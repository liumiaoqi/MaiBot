import { useSpring, animated } from '@react-spring/web'

import { useTranslation } from 'react-i18next'

import type { InnerActivityData } from '../utils/vital-signs'

interface InnerActivityIndicatorProps {
  data: InnerActivityData
}

export function InnerActivityIndicator({ data }: InnerActivityIndicatorProps) {
  const { t } = useTranslation()

  const isIntrospecting = data.status === 'introspecting'

  const spring = useSpring({
    from: { opacity: 0.1 },
    to: { opacity: 0.3 },
    loop: isIntrospecting,
    config: { duration: 2000 },
    reverse: isIntrospecting,
    immediate: !isIntrospecting,
  })

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <animated.span
        className="w-2.5 h-2.5 rounded-full bg-violet-400"
        style={{ opacity: spring.opacity }}
      />
      <span className="text-muted-foreground">
        {t(`agent.vitalSigns.innerActivity.${data.status}`)}
      </span>
    </div>
  )
}