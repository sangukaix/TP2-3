import { useId, useState } from 'react'

// Plain-language examples, not measured subcategory amounts or causal forecasts.
const EXAMPLES = {
  운송: ['항공 이동: 항공권 구입', '수상 이동: 여객선·배편 이용', '육상 이동: 철도·버스 등 여객 교통 이용', '차량 대여: 렌터카 이용'],
  쇼핑: ['면세점에서 상품 구입', '백화점·쇼핑몰 등에서 의류와 생활용품 구입', '여행 중 선물·기념품·지역 상품 구입'],
  식음료: ['음식점에서 식사', '카페에서 커피·음료 구입', '제과점·간식점 등에서 먹거리 구입'],
  숙박: ['호텔·리조트 객실 이용', '펜션·민박·게스트하우스 숙박', '모텔 등 기타 숙박시설 이용'],
  여가서비스: ['관광·문화시설 입장권', '공연·전시 등 관람', '레저·스포츠·체험시설 이용'],
  여행: ['여행사에서 여행상품 예약', '여행사의 관광 프로그램·여행 서비스 이용'],
  의료웰니스: ['의료기관의 진료·검진 등 건강 관련 서비스', '건강관리·휴식 목적의 웰니스 서비스 이용'],
}

export default function ConsumptionCategoryHelp({ category, index, amountLabel }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const key = Object.keys(EXAMPLES).find((name) => category.name.replace(/\s/g, '').includes(name))
  const examples = EXAMPLES[key] ?? ['원자료에서 이 업종으로 분류한 가맹점의 상품·서비스 결제']
  return (
    <div className="consumption-category consumption-category--explained">
      <div className="consumption-category-name">
        <i aria-hidden="true">{index + 1}</i>
        <span>{category.name}</span>
        <button type="button" className="consumption-help-toggle" aria-label={`${category.name} 소비 항목 설명`}
          aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}
          onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false) }}>?</button>
      </div>
      <b>{category.share.toFixed(1)}%</b>
      <small>{amountLabel}</small>
      {open && <div id={id} className="consumption-help-content" role="region" aria-label={`${category.name} 소비 예시`}>
        <strong>{category.name}에서는 어떤 지출을 하나요?</strong>
        <ul>{examples.map((example) => <li key={example}>{example}</li>)}</ul>
        <p>이해를 돕는 이용 예시입니다. 실제 포함 업종은 카드사·자료 기준에 따르며, 위 항목별 금액이나 증가 원인을 측정한 목록은 아닙니다.</p>
        {key === '운송' && <p>이동 관련 결제입니다. 항공사·운송사의 결제 귀속 지역이 실제 여행지와 같다고 단정할 수는 없습니다.</p>}
        {key === '의료웰니스' && <p>모든 의료·건강관리 결제를 관광 목적 지출로 해석하지 않습니다.</p>}
        <a href="https://datalab.visitkorea.or.kr/datalab/portal/getMetaInfoList.do" target="_blank" rel="noreferrer">한국관광 데이터랩 데이터 설명 ↗</a>
      </div>}
    </div>
  )
}
