/**
 * Where the cursor grips the pet while dragging: dead centre, always.
 *
 * Not an art-relative offset: a grip near the front of the body, mirrored with it,
 * makes the pet hang off the pointer at an angle that changes with facing, and the
 * drag then needs its own "held" drawing to look deliberate. With a centred grip the
 * pet simply follows the cursor, which is also the only sane answer for a custom
 * pack whose art we know nothing about.
 */
import { PET_W, PET_H } from './constants'

export type GripInput = { flipped?: boolean; custom?: boolean }

export function dragGrip(_opts: GripInput = {}): { x: number; y: number } {
  return { x: PET_W / 2, y: PET_H / 2 }
}
