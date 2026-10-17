type Name =
  | 'upload'
  | 'video'
  | 'rules'
  | 'status'
  | 'check'
  | 'alert'
  | 'arrow'
  | 'lock'
  | 'close'
  | 'menu'
  | 'search'
  | 'external'
  | 'clock'
  | 'expand'
  | 'chevron'
  | 'trash'
const paths: Record<Name, string> = {
  upload: 'M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5',
  video: 'M3 5h13v14H3zM16 9l5-3v12l-5-3',
  rules: 'M4 3h12l4 4v14H4zM16 3v5h4M8 12h8M8 16h6',
  status: 'M3 12h4l3-8 4 16 3-8h4',
  check: 'm5 12 4 4L19 6',
  alert: 'M12 8v5m0 4h.01M12 3 2 21h20z',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  lock: 'M5 10h14v11H5zM8 10V6a4 4 0 0 1 8 0v4',
  close: 'm6 6 12 12M6 18 18 6',
  menu: 'M3 6h18M3 12h18M3 18h18',
  search: 'M21 21l-6-6M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
  external: 'M14 3h7v7m0-7L10 14M10 3H3v18h18v-7',
  clock: 'M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
  expand: 'M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6',
  chevron: 'm9 5 7 7-7 7',
  trash: 'M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7',
}
export function Icon({ name, size = 20 }: { name: Name; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  )
}
