import React from 'react'
import hekmaLogoSvg from '../assets/logo.svg'

interface HekmaLogoProps {
  collapsed?: boolean
  height?: number
  className?: string
}

export function HekmaLogo({ collapsed = false, height = 38, className = '' }: HekmaLogoProps) {
  if (collapsed) {
    return (
      <div 
        style={{ 
          width: `${height}px`, 
          height: `${height}px`, 
          overflow: 'hidden',
          display: 'flex',
          alignItems: 'center',
          flexShrink: 0
        }}
        className={className}
      >
        <img 
          src={hekmaLogoSvg} 
          alt="HEKMA" 
          style={{ 
            height: `${height}px`, 
            maxWidth: 'none',
            objectFit: 'cover',
            objectPosition: 'left center'
          }} 
        />
      </div>
    )
  }

  return (
    <img 
      src={hekmaLogoSvg} 
      alt="HEKMA" 
      height={height}
      className={className}
      style={{ 
        height: `${height}px`, 
        maxHeight: `${height}px`,
        maxWidth: '170px',
        display: 'block',
        objectFit: 'contain'
      }} 
    />
  )
}
