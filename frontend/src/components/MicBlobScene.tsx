import { Environment, Points, PointMaterial } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import { Bloom, EffectComposer, Noise, Vignette } from '@react-three/postprocessing'
import { useMemo, useRef } from 'react'
import { Group } from 'three'

type MicBlobSceneProps = {
  volumeLevel: number
  frequencyBands: {
    bass: number
    mid: number
    treble: number
  }
}

function ParticleBlob({ volumeLevel, frequencyBands }: MicBlobSceneProps) {
  const groupRef = useRef<Group>(null)
  const outerRef = useRef<Group>(null)
  const innerRef = useRef<Group>(null)
  const haloRef = useRef<Group>(null)

  const [positions, scales] = useMemo(() => {
    const pointsCount = 2400
    const points = new Float32Array(pointsCount * 3)
    const pointScales = new Float32Array(pointsCount)

    // A seedable LCG random number generator to satisfy react-hooks/purity
    let seed = 4523
    const pureRand = () => {
      seed = (1664525 * seed + 1013904223) % 4294967296
      return seed / 4294967296
    }

    for (let i = 0; i < pointsCount; i += 1) {
      const radius = 2.2 + pureRand() * 0.8
      const theta = pureRand() * Math.PI * 2
      const phi = Math.acos(2 * pureRand() - 1)
      const idx = i * 3

      points[idx] = radius * Math.sin(phi) * Math.cos(theta)
      points[idx + 1] = radius * Math.sin(phi) * Math.sin(theta)
      points[idx + 2] = radius * Math.cos(phi)
      pointScales[i] = 0.5 + pureRand()
    }
    return [points, pointScales]
  }, [])

  useFrame(({ clock }) => {
    const group = groupRef.current
    const outer = outerRef.current
    const inner = innerRef.current
    const halo = haloRef.current
    if (!group) {
      return
    }

    const t = clock.getElapsedTime()
    const bass = Math.min(frequencyBands.bass, 1.6)
    const mid = Math.min(frequencyBands.mid, 1.6)
    const treble = Math.min(frequencyBands.treble, 1.6)

    // Add a gentle breathing heartbeat when no audio or mic input is active
    const isIdle = volumeLevel < 0.01 && bass < 0.01 && mid < 0.01 && treble < 0.01
    const idlePulse = isIdle ? Math.sin(t * 1.5) * 0.025 : 0

    const pulse = 1 + Math.min(volumeLevel, 1.5) * 0.28 + idlePulse
    group.rotation.y = t * 0.16
    group.rotation.x = Math.sin(t * 0.2 + mid) * 0.12
    group.scale.set(
      1 + bass * 0.13 + idlePulse,
      pulse + mid * 0.14,
      1 + treble * 0.13 + idlePulse
    )

    if (outer) {
      outer.rotation.y = -t * 0.22
      outer.scale.setScalar(1 + bass * 0.28 + idlePulse)
    }
    if (inner) {
      inner.rotation.x = t * 0.25
      inner.rotation.z = -t * 0.18
      inner.scale.set(
        1 + mid * 0.18 + idlePulse,
        1 + treble * 0.16 + idlePulse,
        1 + mid * 0.1 + idlePulse
      )
    }
    if (halo) {
      halo.rotation.y = t * 0.35
      halo.scale.setScalar(1 + treble * 0.32 + idlePulse)
    }
  })

  return (
    <group ref={groupRef}>
      <group ref={outerRef}>
        <Points positions={positions} stride={3} frustumCulled={false}>
          <PointMaterial
            transparent
            color="#58f6ff"
            size={0.048}
            sizeAttenuation
            depthWrite={false}
            opacity={0.88}
          />
        </Points>
      </group>
      <group ref={innerRef}>
        <Points positions={positions} sizes={scales} stride={3} frustumCulled={false}>
          <PointMaterial
            transparent
            color="#ff66ff"
            size={0.018}
            sizeAttenuation
            depthWrite={false}
            opacity={0.7}
          />
        </Points>
      </group>
      <group ref={haloRef}>
        <Points positions={positions} stride={3} frustumCulled={false}>
          <PointMaterial
            transparent
            color="#93c5fd"
            size={0.022}
            sizeAttenuation
            depthWrite={false}
            opacity={0.4}
          />
        </Points>
      </group>
    </group>
  )
}

export function MicBlobScene({ volumeLevel, frequencyBands }: MicBlobSceneProps) {
  return (
    <Canvas camera={{ position: [0, 0, 7], fov: 55 }}>
      <color attach="background" args={['#040508']} />
      <ambientLight intensity={0.4} />
      <directionalLight position={[4, 4, 4]} intensity={1.1} color="#7dd3fc" />
      <directionalLight position={[-4, -3, -2]} intensity={0.4} color="#d946ef" />
      <ParticleBlob volumeLevel={volumeLevel} frequencyBands={frequencyBands} />
      <Environment preset="city" />
      <EffectComposer multisampling={4}>
        <Bloom luminanceThreshold={0.08} luminanceSmoothing={0.65} intensity={1.1} />
        <Noise opacity={0.04} />
        <Vignette eskil={false} offset={0.18} darkness={0.72} />
      </EffectComposer>
    </Canvas>
  )
}
