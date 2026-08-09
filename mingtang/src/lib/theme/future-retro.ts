import type { FutureRetroStyleConfig, FutureRetroTextureStyle, ThemeTokenOverride } from './tokens'
import { futureRetroLightTokens, futureRetroDarkTokens } from './tokens'
import { hexToHSL, hslToHex, parseHSL, formatHSL } from './palette'

function svgDataUrl(svg: string) {
	return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`
}

/**
* 生成未来复古纸面纹理。纹理通过 CSS 变量应用到外壳、顶栏和浮层，
* 因而切换配置时无需重建组件树。
*/
export function buildFutureRetroTexture(
	style: FutureRetroTextureStyle,
	intensity: number,
	dark: boolean
) {
	if (style === 'none' || intensity <= 0) {
		return 'none'
	}

	const strength = Math.max(0, Math.min(100, intensity)) / 100
	const ink = dark ? '#d2c0a9' : '#6b3b1c'
	const accent = dark ? '#c04d27' : '#c24d24'

	if (style === 'dot-grid') {
		return svgDataUrl(
			`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><circle cx="2" cy="2" r="0.8" fill="${ink}" opacity="${(0.34 * strength).toFixed(3)}"/></svg>`
		)
	}

	if (style === 'ruled') {
		return svgDataUrl(
			`<svg xmlns="http://www.w3.org/2000/svg" width="40" height="28"><path d="M0 27.5H40" stroke="${ink}" stroke-width="0.7" opacity="${(0.28 * strength).toFixed(3)}"/></svg>`
		)
	}

	const coarse = style === 'coarse'
	const size = coarse ? 260 : 180
	const frequency = coarse ? '0.32' : '1.05'
	const octaves = coarse ? 3 : 4
	// 细颗粒在高分屏缩放后容易被纸张亮度层稀释，因此需要略高的基础对比度。
	const noiseOpacity = (strength * (coarse ? 0.28 : 0.3)).toFixed(3)
	const fleckOpacity = (strength * (coarse ? 0.2 : 0.16)).toFixed(3)

	return svgDataUrl(
		`<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="${frequency}" numOctaves="${octaves}" seed="11"/></filter><rect width="100%" height="100%" filter="url(#n)" opacity="${noiseOpacity}"/><g fill="${accent}" opacity="${fleckOpacity}"><circle cx="12" cy="21" r="${coarse ? 1.5 : 0.7}"/><circle cx="67" cy="43" r="${coarse ? 1.1 : 0.55}"/><circle cx="139" cy="16" r="${coarse ? 1.35 : 0.65}"/></g></svg>`
	)
}

/**
 * 根据 future-retro 五维配置生成 token 覆盖（TE-1-3 纹理参数注入 pipeline）。
 * 输入 FutureRetroStyleConfig + isDark，输出 Partial<ThemeTokens>。
 * - 纹理背景 → color['background-texture']
 * - 纸暖度 → 调整 color.background 色温（HSL 调 H 向暖色偏移）
 * - 面板深度 → 调整 color.card / color.popover 明度
 * - 描边比例 → 调整 color.border 明度
 */
export function futureRetroTokenOverrides(
	config: FutureRetroStyleConfig,
	isDark: boolean,
): ThemeTokenOverride {
	const baseTokens = isDark ? futureRetroDarkTokens : futureRetroLightTokens
	const baseColor = baseTokens.color!

	// 纹理背景
	const texture = buildFutureRetroTexture(config.textureStyle, config.textureIntensity, isDark)

	// 纸暖度：0-100，默认 100。低于 100 时向暖色（H=30）偏移
	// 偏移量取全量（早期 *0.5 系数最多移 5.4° 色相——人眼不可感知，用户"不知道看哪里"的根源之一）
	const warmthFactor = (100 - config.paperWarmth) / 100
	const bgHsl = parseHSL(hexToHSL(baseColor.background))
	const warmH = bgHsl.h + (30 - bgHsl.h) * warmthFactor
	const warmS = bgHsl.s + (30 - bgHsl.s) * warmthFactor * 0.4
	const adjustedBg = hslToHex(formatHSL(warmH, warmS, bgHsl.l))

	// 面板深度：0-100，默认 100。低于 100 时加深（暗模式）或提亮（亮模式）
	const depthFactor = (100 - config.panelDepth) / 100
	const cardHsl = parseHSL(hexToHSL(baseColor.card))
	const cardL = isDark ? cardHsl.l * (1 - depthFactor * 0.3) : cardHsl.l + depthFactor * 10
	const adjustedCard = hslToHex(formatHSL(cardHsl.h, cardHsl.s, cardL))

	const popoverHsl = parseHSL(hexToHSL(baseColor.popover))
	const popoverL = isDark ? popoverHsl.l * (1 - depthFactor * 0.3) : popoverHsl.l + depthFactor * 10
	const adjustedPopover = hslToHex(formatHSL(popoverHsl.h, popoverHsl.s, popoverL))

	// 描边比例：50-100，默认 100。低于 100 时降低对比度
	const strokeFactor = config.strokeScale / 100
	const borderHsl = parseHSL(hexToHSL(baseColor.border))
	const borderL = isDark
		? borderHsl.l * (0.5 + strokeFactor * 0.5)
		: borderHsl.l + (1 - strokeFactor) * 10
	const adjustedBorder = hslToHex(formatHSL(borderHsl.h, borderHsl.s, borderL))

	// 基础字号：baseFontSize（px，12-20）→ 6 个 text token
	// （对齐原版 buildFontSizeTokens 比例——base×0.75/0.875/1/1.125/1.25/1.5）
	const baseRem = (config.baseFontSize ?? 16) / 16
	const adjustedText = {
		xs: `${(baseRem * 0.75).toFixed(4)}rem`,
		sm: `${(baseRem * 0.875).toFixed(4)}rem`,
		base: `${baseRem.toFixed(4)}rem`,
		lg: `${(baseRem * 1.125).toFixed(4)}rem`,
		xl: `${(baseRem * 1.25).toFixed(4)}rem`,
		'2xl': `${(baseRem * 1.5).toFixed(4)}rem`,
	}

	return {
		color: {
			'background-texture': texture,
			background: adjustedBg,
			card: adjustedCard,
			'card-foreground': baseColor['card-foreground'],
			popover: adjustedPopover,
			'popover-foreground': baseColor['popover-foreground'],
			border: adjustedBorder,
		},
		text: adjustedText,
	}
}
