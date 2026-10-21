import artwork from '../assets/brand/footie-wordmark-forest-v1.webp'

/** Frame the approved transparent artwork without its presentation margins.
 * This is a raster concept preview, not a vector recreation of the lettering.
 * The containing home link supplies the accessible name. */
export function FootieWordmark() {
  return <svg className="cp-wordmark" viewBox="100 112 1990 516" aria-hidden="true" focusable="false">
    <image href={artwork} width="2172" height="724"/>
  </svg>
}
