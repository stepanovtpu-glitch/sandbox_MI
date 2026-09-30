/**
 * Единая точка бренда приложения.
 *
 * Эмблема, название компании и фоновые фотографии подключаются только отсюда,
 * чтобы замена на официальный комплект из корпоративного портала («Архимед»)
 * свелась к правке одного файла и замене файлов в assets/brand — без поиска
 * импортов по экранам. Цветовые токены бренда — в theme.css (--ink-*).
 *
 * Эмблема — из корпоративного портала «Архимед» (app/static/ink_logo.svg): зелёный
 * овал #026958 с белым знаком, одинаково читается на тёмном и светлом фоне.
 * Фотографии — «Чёрный лёд Байкала» и «Разломы во льду» (CC BY-SA 4.0 / CC BY 4.0,
 * авторы указаны в assets/photos/LICENSES-archimed.md и в подвале навигации).
 */
import inkEmblem from './assets/brand/ink-emblem-archimed.svg';
import inkLogoFullWhite from './assets/brand/ink-logo-full-white.svg';

export const BRAND = {
  productName: 'GasMeter Pro',
  companyName: 'Иркутская нефтяная компания',
  companyNameFull: 'ООО «Иркутская нефтяная компания»',
  /** Эмблема для светлого фона */
  logo: inkEmblem,
  /** Эмблема для тёмного фона (та же: овал сам задаёт фон знака) */
  logoOnDark: inkEmblem,
  /** Полная эмблема с названием, для тёмного фона (экран входа, титулы) */
  logoFullOnDark: inkLogoFullWhite,
  logoAlt: 'Эмблема ИНК',
  /** Обязательное указание авторства фотографий (CC BY-SA 4.0, CC BY 4.0) */
  photoCredit: 'Фото: Sergey Pesterev, Anastasiia Starikova · CC BY-SA 4.0 / CC BY 4.0',
} as const;

/** Эмблема под текущую тему интерфейса. */
export function brandLogo(theme: 'dark' | 'light'): string {
  return theme === 'light' ? BRAND.logo : BRAND.logoOnDark;
}
