import { useState } from 'react'
import { Building2, LockKeyhole, Mail, Phone, UserRound } from 'lucide-react'
import HeaderActions from '../components/HeaderActions'
import '../App.css'
import './Signup.css'
import logo from '../assets/logo5.png'

const MUNICIPALITIES = {
  서울특별시: ['강남구', '마포구', '서대문구', '송파구', '용산구', '종로구'],
  부산광역시: ['기장군', '부산진구', '수영구', '영도구', '해운대구'],
  경기도: ['고양시', '수원시', '양평군', '용인시', '파주시'],
  강원특별자치도: ['강릉시', '속초시', '양양군', '춘천시', '평창군'],
  제주특별자치도: ['서귀포시', '제주시'],
}

const SECURITY_QUESTIONS = [
  '내가 졸업한 초등학교는?',
  '나의 첫사랑 이름은?',
  '나의 애완동물 이름은?',
  '나의 첫 직장명은?',
]

const CUSTOM_SECURITY_QUESTION = 'custom'
const VISIBLE_ASCII_PATTERN = /^[!-~]+$/

function isValidAccountText(value, minLength, maxLength) {
  return value.length >= minLength
    && value.length <= maxLength
    && VISIBLE_ASCII_PATTERN.test(value)
}

// TODO: 추후 전국 행정구역 데이터/API 연결
const INITIAL_FORM = {
  userId: '',
  password: '',
  passwordConfirm: '',
  phone: '',
  email: '',
  province: '',
  municipality: '',
  securityQuestionType: '',
  customSecurityQuestion: '',
  securityAnswer: '',
}

function validate(formData) {
  const nextErrors = {}
  const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

  if (!formData.userId.trim()) {
    nextErrors.userId = '사용할 아이디를 입력해주세요.'
  } else if (!isValidAccountText(formData.userId, 6, 12)) {
    nextErrors.userId = '아이디는 6~12자의 영문, 숫자, 특수문자로 입력해주세요.'
  }
  if (!formData.password) {
    nextErrors.password = '비밀번호를 입력해주세요.'
  } else if (!isValidAccountText(formData.password, 4, 12)) {
    nextErrors.password = '비밀번호는 4~12자의 영문, 숫자, 특수문자로 입력해주세요.'
  }
  if (!formData.passwordConfirm) {
    nextErrors.passwordConfirm = '비밀번호를 한 번 더 입력해주세요.'
  } else if (formData.password !== formData.passwordConfirm) {
    nextErrors.passwordConfirm = '비밀번호가 일치하지 않습니다.'
  }
  if (!formData.email.trim()) {
    nextErrors.email = '이메일을 입력해주세요.'
  } else if (!emailPattern.test(formData.email.trim())) {
    nextErrors.email = '올바른 이메일 형식으로 입력해주세요.'
  }
  if (!formData.province) {
    nextErrors.municipality = '시/도를 선택해주세요.'
  } else if (!formData.municipality) {
    nextErrors.municipality = '시/군/구를 선택해주세요.'
  }
  if (!formData.securityQuestionType) {
    nextErrors.securityQuestionType = '힌트 질문을 선택해주세요.'
  }
  if (formData.securityQuestionType === CUSTOM_SECURITY_QUESTION) {
    const customQuestion = formData.customSecurityQuestion.trim()
    if (!customQuestion) {
      nextErrors.customSecurityQuestion = '힌트 질문을 입력해주세요.'
    } else if (customQuestion.length > 20) {
      nextErrors.customSecurityQuestion = '힌트 질문은 20자 이내로 입력해주세요.'
    }
  }
  if (!formData.securityAnswer.trim()) {
    nextErrors.securityAnswer = '힌트 답변을 입력해주세요.'
  }

  return nextErrors
}

export default function Signup() {
  const [formData, setFormData] = useState(INITIAL_FORM)
  const [errors, setErrors] = useState({})
  const [isValidated, setIsValidated] = useState(false)

  const handleChange = ({ target: { name, value } }) => {
    setFormData((current) => {
      if (name === 'province') return { ...current, province: value, municipality: '' }
      if (name === 'securityQuestionType') {
        return { ...current, securityQuestionType: value, customSecurityQuestion: '' }
      }
      return { ...current, [name]: value }
    })
    setErrors((current) => {
      const nextErrors = { ...current }
      delete nextErrors[name]
      if (name === 'province') delete nextErrors.municipality
      if (name === 'password') delete nextErrors.passwordConfirm
      if (name === 'securityQuestionType') delete nextErrors.customSecurityQuestion
      return nextErrors
    })
    setIsValidated(false)
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    const nextErrors = validate(formData)
    setErrors(nextErrors)
    setIsValidated(false)

    if (Object.keys(nextErrors).length > 0) {
      const firstError = Object.keys(nextErrors)[0]
      const firstInvalidId = firstError === 'municipality' && !formData.province ? 'province' : firstError
      if (firstError === 'userId' && formData.userId.trim()) {
        alert('아이디는 6~12자의 영문, 숫자, 특수문자로 입력해주세요.')
      } else if (firstError === 'password' && formData.password) {
        alert('비밀번호는 4~12자의 영문, 숫자, 특수문자로 입력해주세요.')
      }
      const firstInvalidField = document.getElementById(firstInvalidId)
      firstInvalidField?.focus()
      return
    }

    const {
      province,
      passwordConfirm: _passwordConfirm,
      securityQuestionType,
      customSecurityQuestion,
      securityAnswer,
      ...values
    } = formData
    const securityQuestion = securityQuestionType === CUSTOM_SECURITY_QUESTION
      ? customSecurityQuestion.trim()
      : securityQuestionType
    const signupPayload = {
      ...values,
      userId: values.userId.trim(),
      phone: values.phone.trim() || null,
      email: values.email.trim(),
      municipality: `${province} ${values.municipality}`,
      securityQuestion,
      securityAnswer: securityAnswer.trim(),
    }

    // TODO: 회원가입 API 연결
    console.log('signup form:', signupPayload)
    setIsValidated(true)
  }

  const navigateHome = (event) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    window.history.pushState({}, '', '/')
    window.dispatchEvent(new PopStateEvent('popstate'))
    window.scrollTo({ top: 0 })
  }

  const navigateLogin = (event) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    window.history.pushState({}, '', '/login')
    window.dispatchEvent(new PopStateEvent('popstate'))
    window.scrollTo({ top: 0 })
  }

  const municipalityOptions = formData.province ? MUNICIPALITIES[formData.province] : []

  return (
    <main className="signup-page">
      <header className="signup-header">
        <a className="signup-logo-link" href="/" onClick={navigateHome} aria-label="OLIGO-K 홈으로 이동">
          <img className="signup-logo" src={logo} alt="OLIGO-K" />
        </a>
        <HeaderActions />
      </header>

      <section className="signup-content" aria-labelledby="signup-title">
        <div className="signup-card">
          <div className="signup-card-heading">
            <h1 id="signup-title">회원가입</h1>
            <p>OLIGO-K와 함께 지역의 가능성을 올려보세요!</p>
          </div>

          <form className="signup-form" onSubmit={handleSubmit} noValidate>
            <div className="signup-field">
              <label htmlFor="userId"><UserRound size={17} />사용할 아이디 <b>필수</b></label>
              <span className="signup-help" id="userId-help">6~12자 / 영문·숫자·특수문자 사용 가능</span>
              <input id="userId" name="userId" type="text" autoComplete="username"
                value={formData.userId} onChange={handleChange} minLength={6} maxLength={12} required
                placeholder="사용할 아이디를 입력해주세요"
                aria-invalid={Boolean(errors.userId)}
                aria-describedby={errors.userId ? 'userId-help userId-error' : 'userId-help'} />
              {errors.userId && <small className="signup-error" id="userId-error" role="alert">{errors.userId}</small>}
            </div>

            <div className="signup-password-grid">
              <div className="signup-field">
                <label htmlFor="password"><LockKeyhole size={17} />비밀번호 <b>필수</b></label>
                <span className="signup-help" id="password-help">4~12자 / 영문·숫자·특수문자 사용 가능</span>
                <input id="password" name="password" type="password" autoComplete="new-password"
                  value={formData.password} onChange={handleChange} minLength={4} maxLength={12}
                  placeholder="비밀번호를 입력해주세요" required aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? 'password-help password-error' : 'password-help'} />
                {errors.password && <small className="signup-error" id="password-error" role="alert">{errors.password}</small>}
              </div>
              <div className="signup-field">
                <label htmlFor="passwordConfirm"><LockKeyhole size={17} />비밀번호 확인 <b>필수</b></label>
                <span className="signup-help" id="passwordConfirm-help">4~12자 / 영문·숫자·특수문자 사용 가능</span>
                <input id="passwordConfirm" name="passwordConfirm" type="password" autoComplete="new-password"
                  value={formData.passwordConfirm} onChange={handleChange} minLength={4} maxLength={12}
                  placeholder="비밀번호를 다시 입력해주세요" required
                  aria-invalid={Boolean(errors.passwordConfirm)}
                  aria-describedby={errors.passwordConfirm
                    ? 'passwordConfirm-help passwordConfirm-error'
                    : 'passwordConfirm-help'} />
                {errors.passwordConfirm && <small className="signup-error" id="passwordConfirm-error" role="alert">{errors.passwordConfirm}</small>}
              </div>
            </div>

            <div className="signup-contact-grid">
              <div className="signup-field">
                <label htmlFor="phone"><Phone size={17} />전화번호 <em>선택</em></label>
                <input id="phone" name="phone" type="tel" autoComplete="tel"
                  value={formData.phone} onChange={handleChange} placeholder="010-1234-5678" />
              </div>
              <div className="signup-field">
                <label htmlFor="email"><Mail size={17} />이메일 <b>필수</b></label>
                <span className="signup-help">사업보고서를 받아보실 이메일 주소</span>
                <input id="email" name="email" type="email" autoComplete="email"
                  value={formData.email} onChange={handleChange} placeholder="example@email.com" required
                  aria-invalid={Boolean(errors.email)} aria-describedby={errors.email ? 'email-error' : 'email-help'} />
                <span className="signup-sr-only" id="email-help">사업보고서를 받아보실 이메일 주소</span>
                {errors.email && <small className="signup-error" id="email-error" role="alert">{errors.email}</small>}
              </div>
            </div>

            <fieldset className="signup-fieldset">
              <legend><Building2 size={17} />소속 지자체 또는 관심지역<b>필수</b></legend>
              <div className="signup-select-grid">
                <label className="signup-sr-only" htmlFor="province">시/도 선택</label>
                <select id="province" name="province" value={formData.province} onChange={handleChange}
                  required
                  aria-invalid={Boolean(errors.municipality)} aria-describedby={errors.municipality ? 'municipality-error' : undefined}>
                  <option value="">시/도 선택</option>
                  {Object.keys(MUNICIPALITIES).map((province) => <option value={province} key={province}>{province}</option>)}
                </select>
                <label className="signup-sr-only" htmlFor="municipality">시/군/구 선택</label>
                <select id="municipality" name="municipality" value={formData.municipality}
                  onChange={handleChange} disabled={!formData.province} required
                  aria-invalid={Boolean(errors.municipality)} aria-describedby={errors.municipality ? 'municipality-error' : undefined}>
                  <option value="">시/군/구 선택</option>
                  {municipalityOptions.map((municipality) => <option value={municipality} key={municipality}>{municipality}</option>)}
                </select>
              </div>
              {errors.municipality && <small className="signup-error" id="municipality-error" role="alert">{errors.municipality}</small>}
            </fieldset>

            <fieldset className="signup-fieldset">
              <legend><LockKeyhole size={17} />비밀번호 찾기 힌트 질문 <b>필수</b></legend>
              <div className="signup-security-fields">
                <div className="signup-field">
                  <label htmlFor="securityQuestionType">힌트 질문</label>
                  <select id="securityQuestionType" name="securityQuestionType"
                    value={formData.securityQuestionType} onChange={handleChange} required
                    aria-invalid={Boolean(errors.securityQuestionType)}
                    aria-describedby={errors.securityQuestionType ? 'securityQuestionType-error' : undefined}>
                    <option value="">질문을 선택해주세요</option>
                    {SECURITY_QUESTIONS.map((question) => (
                      <option value={question} key={question}>{question}</option>
                    ))}
                    <option value={CUSTOM_SECURITY_QUESTION}>직접입력</option>
                  </select>
                  {errors.securityQuestionType && (
                    <small className="signup-error" id="securityQuestionType-error" role="alert">
                      {errors.securityQuestionType}
                    </small>
                  )}
                </div>

                {formData.securityQuestionType === CUSTOM_SECURITY_QUESTION && (
                  <div className="signup-field">
                    <label htmlFor="customSecurityQuestion">직접 질문</label>
                    <input id="customSecurityQuestion" name="customSecurityQuestion" type="text"
                      value={formData.customSecurityQuestion} onChange={handleChange}
                      placeholder="20자 이내로 작성해주세요 :)" maxLength={20} required
                      aria-invalid={Boolean(errors.customSecurityQuestion)}
                      aria-describedby={errors.customSecurityQuestion ? 'customSecurityQuestion-error' : undefined} />
                    {errors.customSecurityQuestion && (
                      <small className="signup-error" id="customSecurityQuestion-error" role="alert">
                        {errors.customSecurityQuestion}
                      </small>
                    )}
                  </div>
                )}

                <div className="signup-field">
                  <label htmlFor="securityAnswer">힌트 답변</label>
                  <input id="securityAnswer" name="securityAnswer" type="text"
                    value={formData.securityAnswer} onChange={handleChange}
                    placeholder="답변을 입력해주세요" required
                    aria-invalid={Boolean(errors.securityAnswer)}
                    aria-describedby={errors.securityAnswer ? 'securityAnswer-error' : undefined} />
                  {errors.securityAnswer && (
                    <small className="signup-error" id="securityAnswer-error" role="alert">
                      {errors.securityAnswer}
                    </small>
                  )}
                </div>
              </div>
            </fieldset>

            <button className="signup-submit" type="submit">회원가입</button>
            {isValidated && <p className="signup-success" role="status">입력 확인이 완료되었습니다. API 연결 후 회원가입이 처리됩니다.</p>}

            <p className="signup-login-prompt">
              이미 계정이 있으신가요?{' '}
              <a href="/login" onClick={navigateLogin}>로그인</a>
            </p>
          </form>
        </div>
      </section>
    </main>
  )
}
