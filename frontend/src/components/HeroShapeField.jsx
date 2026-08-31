// 대시보드와 하위 페이지가 같은 배경 애니메이션을 사용하도록 장식 영역을 공통 컴포넌트로 분리합니다.
const HERO_SHAPE_CLASSES = [
  'hero-shape hero-shape--circle hero-shape--one', 'hero-shape hero-shape--square hero-shape--two',
  'hero-shape hero-shape--triangle hero-shape--three', 'hero-shape hero-shape--circle hero-shape--four',
  'hero-shape hero-shape--square hero-shape--five', 'hero-shape hero-shape--triangle hero-shape--six',
  'hero-shape hero-shape--circle hero-shape--seven', 'hero-shape hero-shape--square hero-shape--eight',
  'hero-shape hero-shape--triangle hero-shape--nine', 'hero-shape hero-shape--circle hero-shape--ten',
  'hero-shape hero-shape--square hero-shape--eleven', 'hero-shape hero-shape--triangle hero-shape--twelve',
  'hero-shape hero-shape--circle hero-shape--thirteen', 'hero-shape hero-shape--square hero-shape--fourteen',
  'hero-shape hero-shape--triangle hero-shape--fifteen', 'hero-shape hero-shape--circle hero-shape--sixteen',
  'hero-shape hero-shape--square hero-shape--seventeen', 'hero-shape hero-shape--triangle hero-shape--eighteen',
  'hero-shape hero-shape--circle hero-shape--nineteen', 'hero-shape hero-shape--square hero-shape--twenty',
  'hero-shape hero-shape--triangle hero-shape--twenty-one', 'hero-shape hero-shape--circle hero-shape--twenty-two',
  'hero-shape hero-shape--square hero-shape--twenty-three', 'hero-shape hero-shape--triangle hero-shape--twenty-four',
  'hero-shape hero-shape--circle hero-shape--twenty-five', 'hero-shape hero-shape--square hero-shape--twenty-six',
]

export default function HeroShapeField() {
  return <div className="hero-shape-field" aria-hidden="true">{HERO_SHAPE_CLASSES.map((className) => <span className={className} key={className} />)}</div>
}
