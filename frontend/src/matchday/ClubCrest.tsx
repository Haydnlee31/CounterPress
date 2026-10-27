import { clubName } from './identity'

/** Original vector marks: Eastbridge's stone bridge and Northport's compass/harbour. */
export function ClubCrest({ club, className = 'fan-crest' }: { club: string; className?: string }) {
  return <svg className={className} viewBox="0 0 80 90" role="img" aria-label={`${clubName(club)} crest`}>
    {club === 'eastbridge' ? <>
      <path d="M5 5Q40-2 75 5V49Q73 73 40 87Q7 73 5 49Z" fill="#143f33" stroke="#e7c771" strokeWidth="3" />
      <path d="M13 11Q40 5 67 11V48Q65 67 40 79Q15 67 13 48Z" fill="none" stroke="#e7c771" strokeWidth=".8" />
      <path d="M20 44h40v19H49V52a9 9 0 0 0-18 0v11H20Z M17 40h46v5H17Z M22 28h8v13h-8Z M50 28h8v13h-8Z" fill="#e7c771" />
      <path d="M21 67q9-5 19 0t19 0" fill="none" stroke="#9bbdab" strokeWidth="2" />
      <text x="40" y="23" textAnchor="middle" fill="#fff4cc" fontSize="10" fontFamily="serif" letterSpacing="3">E B</text>
    </> : <>
      <path d="M40 3 75 19v37L40 87 5 56V19Z" fill="#163d68" stroke="#d2e9fa" strokeWidth="3" />
      <path d="M40 10 68 23v30L40 78 12 53V23Z" fill="none" stroke="#7caacc" />
      <path d="m40 20 4 18 15 7-15 6-4 17-5-17-14-6 14-7Z" fill="#e9c675" />
      <path d="m40 20 0 25 19 0-15-7Z M40 45v23l-5-17-14-6Z" fill="#f6fbff" />
      <path d="M22 63q9-6 18 0t18 0M27 69q7-4 13 0t13 0" fill="none" stroke="#b4dff5" strokeWidth="2" />
      <text x="40" y="17" textAnchor="middle" fill="#f6fbff" fontSize="7" letterSpacing="2">N P</text>
    </>}
  </svg>
}
