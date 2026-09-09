import { useState } from 'react'
import { KeyRound, LockKeyhole, Mail, UserRound } from 'lucide-react'
import '../App.css'
import './Login.css'
import logo from '../assets/logo5.png'

const INITIAL_LOGIN = {
  userId: '',
  password: '',
}

const INITIAL_PASSWORD_RECOVERY = {
  userId: '',
  securityAnswer: '',
}

export function maskUserId(userId) {
  const value = String(userId ?? '')
  if (value.length <= 4) return '*'.repeat(Math.max(value.length, 1))
  return `**${value.slice(2, -2)}**`
}

function moveTo(path) {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.scrollTo({ top: 0 })
}

function handlePageLink(path) {
  return (event) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    moveTo(path)
  }
}

export default function Login() {
  const [view, setView] = useState('login')
  const [loginData, setLoginData] = useState(INITIAL_LOGIN)
  const [loginErrors, setLoginErrors] = useState({})
  const [passwordRecovery, setPasswordRecovery] = useState(INITIAL_PASSWORD_RECOVERY)
  const [passwordRecoveryErrors, setPasswordRecoveryErrors] = useState({})
  const [securityQuestion, setSecurityQuestion] = useState('')
  const [questionLookupRequested, setQuestionLookupRequested] = useState(false)
  const [findIdEmail, setFindIdEmail] = useState('')
  const [findIdError, setFindIdError] = useState('')
  const [foundUserId, setFoundUserId] = useState('')

  const changeView = (nextView) => {
    if (nextView === 'findPassword') {
      setPasswordRecovery((current) => ({ ...current, userId: loginData.userId }))
    }
    setView(nextView)
    setLoginErrors({})
    setPasswordRecoveryErrors({})
    setSecurityQuestion('')
    setQuestionLookupRequested(false)
    setFindIdError('')
    setFoundUserId('')
  }

  const handleLoginChange = ({ target: { name, value } }) => {
    setLoginData((current) => ({ ...current, [name]: value }))
    setLoginErrors((current) => {
      const nextErrors = { ...current }
      delete nextErrors[name]
      return nextErrors
    })
  }

  const handleLoginSubmit = (event) => {
    event.preventDefault()
    const nextErrors = {}
    if (!loginData.userId.trim()) nextErrors.userId = '아이디를 입력해주세요.'
    if (!loginData.password) nextErrors.password = '비밀번호를 입력해주세요.'
    setLoginErrors(nextErrors)

    if (Object.keys(nextErrors).length > 0) {
      document.getElementById(Object.keys(nextErrors)[0])?.focus()
      return
    }

    // TODO: 로그인 API 연결
    // Backend 인증 연결 전에만 사용하는 임시 UI 동작입니다.
    alert('로그인 성공! OLIGO-K에 오신 것을 환영합니다! :)')
    moveTo('/')
  }

  const handlePasswordRecoveryChange = ({ target: { name, value } }) => {
    setPasswordRecovery((current) => ({ ...current, [name]: value }))
    setPasswordRecoveryErrors((current) => {
      const nextErrors = { ...current }
      delete nextErrors[name]
      return nextErrors
    })
    if (name === 'userId') {
      setSecurityQuestion('')
      setQuestionLookupRequested(false)
    }
  }

  const handleQuestionLookup = () => {
    if (!passwordRecovery.userId.trim()) {
      setPasswordRecoveryErrors((current) => ({ ...current, userId: '아이디를 입력해주세요.' }))
      document.getElementById('recoveryUserId')?.focus()
      return
    }

    setPasswordRecoveryErrors((current) => {
      const nextErrors = { ...current }
      delete nextErrors.userId
      return nextErrors
    })
    setQuestionLookupRequested(true)
    setSecurityQuestion('')
    // TODO: Backend에서 해당 userId의 securityQuestion 조회
    console.log('security question lookup:', { userId: passwordRecovery.userId.trim() })
  }

  const handleSecurityAnswerSubmit = (event) => {
    event.preventDefault()
    const nextErrors = {}
    if (!passwordRecovery.userId.trim()) nextErrors.userId = '아이디를 입력해주세요.'
    if (!passwordRecovery.securityAnswer.trim()) {
      nextErrors.securityAnswer = '힌트 답변을 입력해주세요.'
    }
    setPasswordRecoveryErrors(nextErrors)

    if (Object.keys(nextErrors).length > 0) {
      const firstErrorId = Object.keys(nextErrors)[0] === 'userId' ? 'recoveryUserId' : 'securityAnswer'
      document.getElementById(firstErrorId)?.focus()
      return
    }

    // TODO: Backend에서 securityAnswer 검증
    // TODO: 답변 검증 성공 시 Backend 비밀번호 재설정 API 연결
    console.log('security answer check:', {
      userId: passwordRecovery.userId.trim(),
      securityAnswer: passwordRecovery.securityAnswer.trim(),
    })
  }

  const handleFindIdSubmit = (event) => {
    event.preventDefault()
    const email = findIdEmail.trim()
    const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

    if (!email) {
      setFindIdError('이메일을 입력해주세요.')
      document.getElementById('findIdEmail')?.focus()
      return
    }
    if (!emailPattern.test(email)) {
      setFindIdError('올바른 이메일 형식으로 입력해주세요.')
      document.getElementById('findIdEmail')?.focus()
      return
    }

    setFindIdError('')
    setFoundUserId('')
    // TODO: 아이디 찾기 API 연결
    // API가 userId를 반환하면 setFoundUserId(response.userId)로 저장합니다.
    console.log('find id:', { email })
  }

  return (
    <main className="login-page">
      <header className="login-header">
        <a className="login-logo-link" href="/" onClick={handlePageLink('/')}
          aria-label="OLIGO-K 홈으로 이동">
          <img className="login-logo" src={logo} alt="OLIGO-K" />
        </a>
      </header>

      <section className="login-content" aria-labelledby="login-title">
        <div className="login-card">
          <div className="login-card-heading">
            <span>OLIGO-K ACCOUNT</span>
            <h1 id="login-title">
              {view === 'login' && '로그인'}
              {view === 'findPassword' && '비밀번호 찾기'}
              {view === 'findId' && '아이디 찾기'}
            </h1>
            <p>
              {view === 'login' && 'OLIGO-K와 함께 지역의 가능성을 올려보세요.'}
              {view === 'findPassword' && '회원가입 당시 설정한 힌트로 본인을 확인합니다.'}
              {view === 'findId' && '회원가입 시 입력하신 이메일 주소를 기재해주세요!'}
            </p>
          </div>

          {view === 'login' && (
            <form className="login-form" onSubmit={handleLoginSubmit} noValidate>
              <div className="login-field">
                <label htmlFor="userId"><UserRound size={17} />아이디 <b>필수</b></label>
                <input id="userId" name="userId" type="text" autoComplete="username"
                  value={loginData.userId} onChange={handleLoginChange}
                  placeholder="아이디를 입력해주세요" required
                  aria-invalid={Boolean(loginErrors.userId)}
                  aria-describedby={loginErrors.userId ? 'userId-error' : undefined} />
                {loginErrors.userId && (
                  <small className="login-error" id="userId-error" role="alert">{loginErrors.userId}</small>
                )}
              </div>

              <div className="login-field">
                <label htmlFor="password"><LockKeyhole size={17} />비밀번호 <b>필수</b></label>
                <input id="password" name="password" type="password" autoComplete="current-password"
                  value={loginData.password} onChange={handleLoginChange}
                  placeholder="비밀번호를 입력해주세요" required
                  aria-invalid={Boolean(loginErrors.password)}
                  aria-describedby={loginErrors.password ? 'password-error' : undefined} />
                {loginErrors.password && (
                  <small className="login-error" id="password-error" role="alert">{loginErrors.password}</small>
                )}
              </div>

              <div className="login-help-links" aria-label="계정 찾기">
                <button type="button" onClick={() => changeView('findPassword')}>
                  비밀번호를 잊어버리셨나요?
                </button>
                <button type="button" onClick={() => changeView('findId')}>
                  아이디를 잊어버리셨나요?
                </button>
              </div>

              <button className="login-submit" type="submit">로그인</button>

              <p className="login-signup-prompt">
                아직 계정이 없으신가요?{' '}
                <a href="/signup" onClick={handlePageLink('/signup')}>회원가입</a>
              </p>
            </form>
          )}

          {view === 'findPassword' && (
            <form className="login-form login-recovery" onSubmit={handleSecurityAnswerSubmit} noValidate>
              <div className="login-field">
                <label htmlFor="recoveryUserId"><UserRound size={17} />아이디 <b>필수</b></label>
                <input id="recoveryUserId" name="userId" type="text" autoComplete="username"
                  value={passwordRecovery.userId} onChange={handlePasswordRecoveryChange}
                  placeholder="아이디를 입력해주세요" required
                  aria-invalid={Boolean(passwordRecoveryErrors.userId)}
                  aria-describedby={passwordRecoveryErrors.userId ? 'recoveryUserId-error' : undefined} />
                {passwordRecoveryErrors.userId && (
                  <small className="login-error" id="recoveryUserId-error" role="alert">
                    {passwordRecoveryErrors.userId}
                  </small>
                )}
              </div>

              <button className="login-secondary-action" type="button" onClick={handleQuestionLookup}>
                힌트 질문 확인
              </button>

              <div className="login-question-panel" aria-live="polite">
                <span><KeyRound size={16} />힌트 질문</span>
                <p>{securityQuestion || '회원가입 당시 설정한 질문이 표시될 영역'}</p>
                {questionLookupRequested && !securityQuestion && (
                  <small>Backend API 연결 후 설정한 질문을 확인할 수 있습니다.</small>
                )}
              </div>

              <div className="login-field">
                <label htmlFor="securityAnswer"><LockKeyhole size={17} />힌트 답변 <b>필수</b></label>
                <input id="securityAnswer" name="securityAnswer" type="text"
                  value={passwordRecovery.securityAnswer} onChange={handlePasswordRecoveryChange}
                  placeholder="답변을 입력해주세요" required
                  aria-invalid={Boolean(passwordRecoveryErrors.securityAnswer)}
                  aria-describedby={passwordRecoveryErrors.securityAnswer ? 'securityAnswer-error' : undefined} />
                {passwordRecoveryErrors.securityAnswer && (
                  <small className="login-error" id="securityAnswer-error" role="alert">
                    {passwordRecoveryErrors.securityAnswer}
                  </small>
                )}
              </div>

              <button className="login-submit" type="submit">답변 확인</button>
              <button className="login-back-button" type="button" onClick={() => changeView('login')}>
                로그인으로 돌아가기
              </button>
            </form>
          )}

          {view === 'findId' && (
            <form className="login-form login-recovery" onSubmit={handleFindIdSubmit} noValidate>
              <div className="login-field">
                <label htmlFor="findIdEmail"><Mail size={17} />이메일 <b>필수</b></label>
                <input id="findIdEmail" name="email" type="email" autoComplete="email"
                  value={findIdEmail} onChange={(event) => {
                    setFindIdEmail(event.target.value)
                    setFindIdError('')
                    setFoundUserId('')
                  }} placeholder="example@email.com" required
                  aria-invalid={Boolean(findIdError)}
                  aria-describedby={findIdError ? 'findIdEmail-error' : undefined} />
                {findIdError && (
                  <small className="login-error" id="findIdEmail-error" role="alert">{findIdError}</small>
                )}
              </div>

              {foundUserId && (
                <p className="login-recovery-result" role="status">
                  아이디는 <strong>{maskUserId(foundUserId)}</strong>입니다!
                </p>
              )}

              <button className="login-submit" type="submit">아이디 찾기</button>
              <button className="login-back-button" type="button" onClick={() => changeView('login')}>
                로그인으로 돌아가기
              </button>
            </form>
          )}
        </div>
      </section>
    </main>
  )
}
