/**
 * Единая точка бренда приложения.
 *
 * Эмблема, название компании и фоновые фотографии подключаются только отсюда,
 * чтобы замена на официальный комплект из корпоративного портала («Архимед»)
 * свелась к правке одного файла и замене файлов в assets/brand — без поиска
 * импортов по экранам. Цветовые токены бренда — в theme.css (--ink-*).
 *
 * Текущие файлы: эмблема с официального сайта ИНК, фотографии зимнего Байкала.
 */
import inkLogo from './assets/brand/ink-logo.svg';
import inkLogoWhite from './assets/brand/ink-logo-white.svg';
import inkLogoFullWhite from './assets/brand/ink-logo-full-white.svg';

export const BRAND = {
  productName: 'GasMeter Pro',
  companyName: 'Иркутская нефтяная компания',
  companyNameFull: 'ООО «Иркутская нефтяная компания»',
  /** Эмблема для светлого фона */
  logo: inkLogo,
  /** Эмблема для тёмного фона */
  logoOnDark: inkLogoWhite,
  /** Полная эмблема с названием, для тёмного фона (экран входа, титулы) */
  logoFullOnDark: inkLogoFullWhite,
  logoAlt: 'Эмблема ИНК',
} as const;

/** Эмблема под текущую тему интерфейса. */
export function brandLogo(theme: 'dark' | 'light'): string {
  return theme === 'light' ? BRAND.logo : BRAND.logoOnDark;
}
