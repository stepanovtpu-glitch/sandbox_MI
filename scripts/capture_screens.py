"""Снимки экранов программы для документации и статей.

Управляет Microsoft Edge в headless-режиме по протоколу CDP: открывает стенд,
подставляет токен сессии, включает светлую тему (она читается на печати)
и сохраняет PNG по каждому сценарию.

Токен передаётся аргументом, чтобы пароль не попадал ни в файл, ни в историю:

    TOKEN=$(curl -s -X POST https://<стенд>/api/auth/login \
        -H 'Content-Type: application/json' \
        -d '{"login":"...","password":"..."}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
    python scripts/capture_screens.py --token "$TOKEN" --out docs/screens
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websockets

EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
PORT = 9333


class Devtools:
    """Минимальный клиент CDP: одна вкладка, команды по очереди."""

    def __init__(self, socket):
        self.socket = socket
        self.counter = 0

    async def call(self, method: str, **params):
        self.counter += 1
        await self.socket.send(json.dumps({'id': self.counter, 'method': method, 'params': params}))
        while True:
            message = json.loads(await self.socket.recv())
            if message.get('id') == self.counter:
                if 'error' in message:
                    raise RuntimeError(f'{method}: {message["error"]}')
                return message.get('result', {})

    async def evaluate(self, expression: str):
        result = await self.call(
            'Runtime.evaluate',
            expression=f'(async () => {{ {expression} }})()',
            awaitPromise=True,
            returnByValue=True,
        )
        return result.get('result', {}).get('value')

    async def shot(self, path: Path, full_page: bool = False):
        params = {'format': 'png'}
        if full_page:
            params['captureBeyondViewport'] = True
        data = await self.call('Page.captureScreenshot', **params)
        path.write_bytes(base64.b64decode(data['data']))
        print(f'  сохранено: {path.name}')


def start_edge(profile: Path) -> subprocess.Popen:
    return subprocess.Popen([
        EDGE,
        '--headless=new',
        f'--remote-debugging-port={PORT}',
        '--remote-allow-origins=*',
        f'--user-data-dir={profile}',
        '--window-size=1600,1000',
        '--hide-scrollbars',
        '--force-device-scale-factor=2',
        'about:blank',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def page_socket() -> str:
    for _ in range(40):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json/list', timeout=1) as response:
                targets = json.load(response)
            pages = [item for item in targets if item.get('type') == 'page']
            if pages:
                return pages[0]['webSocketDebuggerUrl']
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError('Edge не поднял отладочный порт')


NAV = """
const button = [...document.querySelectorAll('.nav-button')].find(item => item.textContent.trim().startsWith(%s));
button?.click();
await new Promise(resolve => setTimeout(resolve, %d));
return document.querySelector('.topbar h1')?.textContent;
"""


async def capture(base_url: str, token: str, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    async with websockets.connect(page_socket(), max_size=40 * 1024 * 1024) as socket:
        page = Devtools(socket)
        await page.call('Page.enable')
        await page.call('Runtime.enable')

        await page.call('Page.navigate', url=base_url)
        await asyncio.sleep(3)
        # Светлая тема «протокол» читается в печати лучше тёмной «диспетчерской»
        await page.evaluate(
            f"localStorage.setItem('gasmeter-token', '{token}');"
            "localStorage.setItem('gasmeter-theme', 'light');"
            "return 'ok';"
        )
        await page.call('Page.navigate', url=base_url)
        await asyncio.sleep(6)

        async def screen(name: str, title: str, wait: float = 2.5, script: str | None = None):
            print(f'{title}…')
            await page.evaluate(NAV % (json.dumps(title, ensure_ascii=False), int(wait * 1000)))
            if script:
                await page.evaluate(script)
            await asyncio.sleep(1.2)
            await page.shot(out / f'{name}.png')

        run_selection = """
        const setField = (label, value) => {
          const field = [...document.querySelectorAll('.field')]
            .find(item => item.querySelector('span')?.textContent.trim().startsWith(label));
          const input = field?.querySelector('input');
          if (!input) return;
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(input, String(value));
          input.dispatchEvent(new Event('input', { bubbles: true }));
        };
        %s
        await new Promise(resolve => setTimeout(resolve, 400));
        [...document.querySelectorAll('button')]
          .find(item => item.textContent.includes('Подобрать МИ'))?.click();
        await new Promise(resolve => setTimeout(resolve, 5000));
        // Прокручивается не окно, а рабочая область экрана
        window.scrollTo(0, 0);
        document.querySelector('.workspace-screen')?.scrollTo(0, 0);
        return 'ok';
        """

        fits = run_selection % (
            "setField('Q min', 60); setField('Q max', 325);"
            "setField('P абс. от', 0.5); setField('P абс. до', 1.5);"
            "setField('T рабочая от', 10); setField('T рабочая до', 60);"
        )
        await screen('01-selection', 'Подбор МИ', script=fits)

        # Тот же экран, прокрученный к составу СИ для службы КИПиА
        await page.evaluate(
            "document.querySelector('.uug-audience')?.scrollIntoView({block:'start'});"
            "await new Promise(resolve => setTimeout(resolve, 800)); return 'ok';"
        )
        await asyncio.sleep(0.8)
        await page.shot(out / '02-composition.png')
        await page.evaluate(
            "window.scrollTo(0, 0);"
            "document.querySelector('.workspace-screen')?.scrollTo(0, 0);"
            "await new Promise(r => setTimeout(r, 500)); return 'ok';"
        )

        # Режим, который парк не обеспечивает: DN 500 от 60 м³/ч
        no_meter = run_selection % (
            # Первый select на форме — измеряемая среда, поэтому DN ищем
            # по наличию нужного значения среди вариантов
            "const dn = [...document.querySelectorAll('.uug-form-panel select')]"
            "  .find(item => [...item.options].some(option => option.value === '500'));"
            "if (dn) {"
            "  const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;"
            "  setter.call(dn, '500');"
            "  dn.dispatchEvent(new Event('change', { bubbles: true }));"
            "}"
            "setField('Q min', 60); setField('Q max', 1000);"
            "setField('P абс. от', 0.5); setField('P абс. до', 0.5);"
            "setField('T рабочая от', 20); setField('T рабочая до', 20);"
        )
        await page.evaluate(no_meter)
        await asyncio.sleep(1.5)
        await page.shot(out / '03-verdict.png')

        # Список остальных методик с вердиктами — виден автоматический контроль
        await page.evaluate(
            "document.querySelector('.uug-alternatives')?.setAttribute('open', '');"
            "await new Promise(resolve => setTimeout(resolve, 400));"
            "document.querySelector('.uug-alternatives')?.scrollIntoView({ block: 'start' });"
            "await new Promise(resolve => setTimeout(resolve, 700)); return 'ok';"
        )
        await asyncio.sleep(0.8)
        await page.shot(out / '09-alternatives.png')

        await screen('04-projects', 'Проекты УУГ')
        await screen('05-library', 'Библиотека МИ')
        await screen('06-intake', 'Добавление МИ')
        await screen('07-calculation', 'Расчёт погрешности')

        # Телефон
        await page.call(
            'Emulation.setDeviceMetricsOverride',
            width=390, height=844, deviceScaleFactor=3, mobile=True,
        )
        await page.call('Page.navigate', url=base_url)
        await asyncio.sleep(6)
        await page.evaluate(NAV % (json.dumps('Подбор МИ', ensure_ascii=False), 2500))
        await asyncio.sleep(1.5)
        await page.shot(out / '08-mobile.png')
        await page.call('Emulation.clearDeviceMetricsOverride')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--token', required=True)
    parser.add_argument('--base-url', default='https://gasmeter.77-95-203-87.sslip.io')
    parser.add_argument('--out', default='docs/screens')
    args = parser.parse_args()

    profile = Path.home() / '.gasmeter-shots-profile'
    edge = start_edge(profile)
    try:
        asyncio.run(capture(args.base_url, args.token, Path(args.out)))
    finally:
        edge.terminate()


if __name__ == '__main__':
    main()
