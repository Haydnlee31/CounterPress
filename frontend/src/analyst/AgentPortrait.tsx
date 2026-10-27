import type {Role} from './data'

/** Original Footie-family portraits. Names outside the SVG identify each specialist. */
export function AgentPortrait({role}:{role:Role|'footie'}){
  const ink=role==='players'?'#66465f':role==='chance'?'#775b1b':role==='defence'?'#365d72':'#214b3b'
  return <svg className="an-agent-portrait" viewBox="0 0 56 56" aria-hidden="true" focusable="false" data-agent={role}>
    <path d="M7 31C7 16 15 7 28 7s21 9 21 24c0 13-9 20-21 20S7 44 7 31Z" fill="#fff4dc"/>
    <path d="M18 9q10-5 20 0l2 8-12 6-12-6Z M8 25l7 4-3 13-5-5Z M48 25l-7 4 3 13 5-5Z" fill={ink}/>
    <ellipse cx="22" cy="32" rx="3" ry="4.5" fill={ink}/><ellipse cx="35" cy="32" rx="3" ry="4.5" fill={ink}/>
    <circle cx="23" cy="30.5" r="1" fill="#fffefa"/><circle cx="36" cy="30.5" r="1" fill="#fffefa"/>
    <path d={role==='chance'?'M25 40q4 7 8 0Z':'M25 41q4 4 8-1'} stroke={ink} strokeWidth="1.8" fill={role==='chance'?ink:'none'} strokeLinecap="round"/>
    {role==='players'&&<g fill="none" stroke={ink} strokeWidth="1.5"><circle cx="22" cy="32" r="7"/><path d="m17 37-4 7"/></g>}
    {role==='control'&&<g fill="none" stroke={ink} strokeWidth="1.5"><rect x="15" y="27" width="12" height="10" rx="3"/><rect x="30" y="27" width="12" height="10" rx="3"/><path d="M27 31h3"/></g>}
    {role==='chance'&&<g fill="none" stroke="#fff4dc" strokeWidth="1.3"><circle cx="28" cy="14" r="4"/><path d="M28 9v3m0 4v3m-5-5h3m4 0h3"/></g>}
    {role==='defence'&&<path d="m24 10 4-1 4 1v5l-4 3-4-3Zm2 3 2 2 3-3" fill="none" stroke="#fff4dc" strokeWidth="1.3" strokeLinejoin="round"/>}
  </svg>
}
