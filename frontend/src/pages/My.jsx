import { useEffect, useState } from 'react'
import {
  Building2, CalendarDays, FileText, KeyRound, LockKeyhole, LogOut, Mail, MapPinned,
  Phone, ShieldCheck, Trash2, Upload, UserRound,
} from 'lucide-react'
import HeaderActions from '../components/HeaderActions'
import '../App.css'
import './My.css'
import logo from '../assets/logo5.png'

const SECURITY_QUESTIONS = [
  '내가 졸업한 초등학교는?',
  '나의 첫사랑 이름은?',
  '나의 애완동물 이름은?',
  '나의 첫 직장명은?',
]

const CUSTOM_QUESTION = 'custom'
const VISIBLE_ASCII_PATTERN = /^[!-~]+$/

const INITIAL_PROFILE = {
  userId: '',
  name: '',
  email: '',
  phone: '',
  province: '',
  municipality: '',
}

const INITIAL_PASSWORD_FORM = {
  currentPassword: '',
  newPassword: '',
  newPasswordConfirm: '',
}

const INITIAL_HINT_FORM = {
  currentPassword: '',
  securityQuestionType: '',
  customSecurityQuestion: '',
  securityAnswer: '',
}

function isValidPassword(value) {
  return value.length >= 4 && value.length <= 12 && VISIBLE_ASCII_PATTERN.test(value)
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

export default function My() {
  const [profile, setProfile] = useState(INITIAL_PROFILE)
  const [isEditingName, setIsEditingName] = useState(!INITIAL_PROFILE.name)
  const [isEditingPhone, setIsEditingPhone] = useState(!INITIAL_PROFILE.phone)
  const [profilePreview, setProfilePreview] = useState('')
  const [securityView, setSecurityView] = useState('')
  const [passwordForm, setPasswordForm] = useState(INITIAL_PASSWORD_FORM)
  const [passwordErrors, setPasswordErrors] = useState({})
  const [hintForm, setHintForm] = useState(INITIAL_HINT_FORM)
  const [hintErrors, setHintErrors] = useState({})

  useEffect(() => () => {
    if (profilePreview) URL.revokeObjectURL(profilePreview)
  }, [profilePreview])

  const handleProfileChange = ({ target: { name, value } }) => {
    setProfile((current) => ({ ...current, [name]: value }))
  }

  const handleProfileImage = (event) => {
    const [file] = event.target.files
    if (!file) return
    setProfilePreview(URL.createObjectURL(file))
    // TODO: 프로필 이미지 업로드 API 연결
  }

  const handleProfileFieldSubmit = (field, setEditing) => {
    const profilePayload = {
      [field]: profile[field].trim() || null,
    }
    // TODO: 회원정보 수정 API 연결
    console.log('profile update:', profilePayload)
    setEditing(false)
  }

  const handleProfileFieldToggle = (field, isEditing, setEditing) => {
    if (isEditing) {
      handleProfileFieldSubmit(field, setEditing)
      return
    }
    setEditing(true)
  }

  const handlePasswordChange = ({ target: { name, value } }) => {
    setPasswordForm((current) => ({ ...current, [name]: value }))
    setPasswordErrors((current) => {
      const nextErrors = { ...current }
      delete nextErrors[name]
      if (name === 'newPassword') delete nextErrors.newPasswordConfirm
      return nextErrors
    })
  }

  const handlePasswordSubmit = (event) => {
    event.preventDefault()
    const nextErrors = {}
    if (!passwordForm.currentPassword) nextErrors.currentPassword = '현재 비밀번호를 입력해주세요.'
    if (!passwordForm.newPassword) nextErrors.newPassword = '새 비밀번호를 입력해주세요.'
    else if (!isValidPassword(passwordForm.newPassword)) {
      nextErrors.newPassword = '4~12자의 영문, 숫자, 특수문자로 입력해주세요.'
    }
    if (!passwordForm.newPasswordConfirm) {
      nextErrors.newPasswordConfirm = '새 비밀번호를 한 번 더 입력해주세요.'
    } else if (passwordForm.newPassword !== passwordForm.newPasswordConfirm) {
      nextErrors.newPasswordConfirm = '새 비밀번호가 일치하지 않습니다.'
    }
    setPasswordErrors(nextErrors)

    if (Object.keys(nextErrors).length > 0) {
      document.getElementById(`my${Object.keys(nextErrors)[0][0].toUpperCase()}${Object.keys(nextErrors)[0].slice(1)}`)?.focus()
      return
    }

    // TODO: 현재 비밀번호 검증 및 비밀번호 변경 API 연결
    console.log('password change form validated')
  }

  const handleHintChange = ({ target: { name, value } }) => {
    setHintForm((current) => name === 'securityQuestionType'
      ? { ...current, securityQuestionType: value, customSecurityQuestion: '' }
      : { ...current, [name]: value })
    setHintErrors((current) => {
      const nextErrors = { ...current }
      delete nextErrors[name]
      if (name === 'securityQuestionType') delete nextErrors.customSecurityQuestion
      return nextErrors
    })
  }

  const handleHintSubmit = (event) => {
    event.preventDefault()
    const nextErrors = {}
    if (!hintForm.currentPassword) nextErrors.currentPassword = '현재 비밀번호를 입력해주세요.'
    if (!hintForm.securityQuestionType) nextErrors.securityQuestionType = '새 힌트 질문을 선택해주세요.'
    if (hintForm.securityQuestionType === CUSTOM_QUESTION && !hintForm.customSecurityQuestion.trim()) {
      nextErrors.customSecurityQuestion = '새 힌트 질문을 입력해주세요.'
    }
    if (!hintForm.securityAnswer.trim()) nextErrors.securityAnswer = '새 힌트 답변을 입력해주세요.'
    setHintErrors(nextErrors)

    if (Object.keys(nextErrors).length > 0) {
      const fieldIds = {
        currentPassword: 'myHintCurrentPassword',
        securityQuestionType: 'mySecurityQuestionType',
        customSecurityQuestion: 'myCustomSecurityQuestion',
        securityAnswer: 'mySecurityAnswer',
      }
      document.getElementById(fieldIds[Object.keys(nextErrors)[0]])?.focus()
      return
    }

    const securityQuestion = hintForm.securityQuestionType === CUSTOM_QUESTION
      ? hintForm.customSecurityQuestion.trim()
      : hintForm.securityQuestionType
    // TODO: 힌트 질문 변경 API 연결
    console.log('security question change form validated:', { securityQuestion })
  }

  const handleLogout = () => {
    // TODO: 로그아웃 API / 인증상태 해제 연결
    console.log('logout requested')
  }

  const handleDeleteAccount = () => {
    if (!window.confirm('정말 회원 탈퇴 절차를 진행하시겠습니까?')) return
    // TODO: 회원 탈퇴 API 연결
    console.log('account deletion requested')
  }

  const profileName = profile.name.trim() || '이름 정보 없음'
  const profileUserId = profile.userId || '아이디 정보 없음'
  const profileRegion = profile.province && profile.municipality
    ? `${profile.province} ${profile.municipality}`
    : '소속 정보 없음'

  return (
    <main className="my-page">
      <header className="my-header">
        <a className="my-logo-link" href="/" onClick={handlePageLink('/')}
          aria-label="OLIGO-K 홈으로 이동">
          <img className="my-logo" src={logo} alt="OLIGO-K" />
        </a>
        <HeaderActions />
      </header>

      <section className="my-content" aria-labelledby="my-title">
        <div className="my-page-heading">          
          <h1 id="my-title">MY PAGE</h1>
          <p>내 계정과 OLIGO-K 이용 정보를 관리합니다.</p>
        </div>

        <section className="my-profile-card" aria-labelledby="my-profile-title">
          <div className="my-profile-image">
            {profilePreview
              ? <img src={profilePreview} alt="선택한 프로필 미리보기" />
              : <UserRound size={44} aria-hidden="true" />}
          </div>
          <div className="my-profile-summary">
            <span id="my-profile-title">PROFILE</span>
            <h2>{profileName}</h2>
            <p>{profileUserId}</p>
            <small><MapPinned size={14} />{profileRegion}</small>
          </div>
          <label className="my-upload-button" htmlFor="myProfileImage">
            <Upload size={15} />사진 선택
          </label>
          <input className="my-file-input" id="myProfileImage" type="file" accept="image/*"
            onChange={handleProfileImage} />
        </section>

        <div className="my-section-grid">
          <section className="my-section my-basic-section" aria-labelledby="my-basic-title">
            <div className="my-section-heading">
              <div><UserRound size={19} /><h2 id="my-basic-title">기본 정보</h2></div>
              <p>회원정보를 확인하고 변경합니다.</p>
            </div>
            <div className="my-form">
              {/* TODO: 로그인 사용자 회원정보 조회 API 연결 */}
              <div className="my-info-list">
                <div className="my-info-row">
                  <span className="my-info-label">아이디</span>
                  <p className="my-info-value">{profile.userId || '미등록'}</p>
                </div>
                <div className="my-info-row">
                  <span className="my-info-label"><Mail size={15} />이메일</span>
                  <p className="my-info-value">{profile.email || '미등록'}</p>
                </div>
                <div className="my-info-row">
                  <span className="my-info-label">이름 <em>선택</em></span>
                  <div className="my-edit-row">
                    {isEditingName ? (
                      <input id="myName" name="name" type="text" value={profile.name}
                        onChange={handleProfileChange} placeholder="이름을 입력해주세요" />
                    ) : <p className="my-info-value">{profile.name || '미등록'}</p>}
                    <button className="my-inline-action" type="button"
                      onClick={() => handleProfileFieldToggle('name', isEditingName, setIsEditingName)}>
                      {isEditingName ? '입력' : '수정'}
                    </button>
                  </div>
                </div>
                <div className="my-info-row">
                  <span className="my-info-label"><Phone size={15} />전화번호 <em>선택</em></span>
                  <div className="my-edit-row">
                    {isEditingPhone ? (
                      <input id="myPhone" name="phone" type="tel" autoComplete="tel" value={profile.phone}
                        onChange={handleProfileChange} placeholder="010-1234-5678" />
                    ) : <p className="my-info-value">{profile.phone || '미등록'}</p>}
                    <button className="my-inline-action" type="button"
                      onClick={() => handleProfileFieldToggle('phone', isEditingPhone, setIsEditingPhone)}>
                      {isEditingPhone ? '입력' : '수정'}
                    </button>
                  </div>
                </div>
                <div className="my-info-row">
                  <span className="my-info-label"><Building2 size={15} />소속 지자체 또는 관심지역</span>
                  <p className="my-info-value">{profileRegion}</p>
                </div>
              </div>
            </div>
          </section>

          <div className="my-side-sections">
            <section className="my-section" aria-labelledby="my-security-title">
              <div className="my-section-heading">
                <div><ShieldCheck size={19} /><h2 id="my-security-title">계정 및 보안</h2></div>
                <p>비밀번호와 힌트 질문을 안전하게 관리합니다.</p>
              </div>
              <div className="my-security-tabs">
                <button type="button" aria-expanded={securityView === 'password'}
                  onClick={() => setSecurityView((current) => current === 'password' ? '' : 'password')}>
                  <LockKeyhole size={16} />비밀번호 변경하기
                </button>
                <button type="button" aria-expanded={securityView === 'hint'}
                  onClick={() => setSecurityView((current) => current === 'hint' ? '' : 'hint')}>
                  <KeyRound size={16} />힌트 질문 변경하기
                </button>
              </div>

              {securityView === 'password' && (
                <form className="my-form my-security-form" onSubmit={handlePasswordSubmit} noValidate>
                  <div className="my-field">
                    <label htmlFor="myCurrentPassword">현재 비밀번호 <b>필수</b></label>
                    <input id="myCurrentPassword" name="currentPassword" type="password"
                      autoComplete="current-password" value={passwordForm.currentPassword}
                      onChange={handlePasswordChange} required aria-invalid={Boolean(passwordErrors.currentPassword)} />
                    {passwordErrors.currentPassword && <small className="my-error" role="alert">{passwordErrors.currentPassword}</small>}
                  </div>
                  <div className="my-field">
                    <label htmlFor="myNewPassword">새 비밀번호 <b>필수</b></label>
                    <small className="my-help">4~12자 / 영문·숫자·특수문자 사용 가능</small>
                    <input id="myNewPassword" name="newPassword" type="password" autoComplete="new-password"
                      minLength={4} maxLength={12} value={passwordForm.newPassword}
                      onChange={handlePasswordChange} required aria-invalid={Boolean(passwordErrors.newPassword)} />
                    {passwordErrors.newPassword && <small className="my-error" role="alert">{passwordErrors.newPassword}</small>}
                  </div>
                  <div className="my-field">
                    <label htmlFor="myNewPasswordConfirm">새 비밀번호 확인 <b>필수</b></label>
                    <input id="myNewPasswordConfirm" name="newPasswordConfirm" type="password"
                      autoComplete="new-password" minLength={4} maxLength={12}
                      value={passwordForm.newPasswordConfirm} onChange={handlePasswordChange} required
                      aria-invalid={Boolean(passwordErrors.newPasswordConfirm)} />
                    {passwordErrors.newPasswordConfirm && <small className="my-error" role="alert">{passwordErrors.newPasswordConfirm}</small>}
                  </div>
                  <button className="my-submit" type="submit">비밀번호 변경</button>
                </form>
              )}

              {securityView === 'hint' && (
                <form className="my-form my-security-form" onSubmit={handleHintSubmit} noValidate>
                  <div className="my-field">
                    <label htmlFor="myHintCurrentPassword">현재 비밀번호 <b>필수</b></label>
                    <input id="myHintCurrentPassword" name="currentPassword" type="password"
                      autoComplete="current-password" value={hintForm.currentPassword}
                      onChange={handleHintChange} required aria-invalid={Boolean(hintErrors.currentPassword)} />
                    {hintErrors.currentPassword && <small className="my-error" role="alert">{hintErrors.currentPassword}</small>}
                  </div>
                  <div className="my-field">
                    <label htmlFor="mySecurityQuestionType">새 힌트 질문 <b>필수</b></label>
                    <select id="mySecurityQuestionType" name="securityQuestionType"
                      value={hintForm.securityQuestionType} onChange={handleHintChange} required
                      aria-invalid={Boolean(hintErrors.securityQuestionType)}>
                      <option value="">질문을 선택해주세요</option>
                      {SECURITY_QUESTIONS.map((question) => (
                        <option value={question} key={question}>{question}</option>
                      ))}
                      <option value={CUSTOM_QUESTION}>직접입력</option>
                    </select>
                    {hintErrors.securityQuestionType && <small className="my-error" role="alert">{hintErrors.securityQuestionType}</small>}
                  </div>
                  {hintForm.securityQuestionType === CUSTOM_QUESTION && (
                    <div className="my-field">
                      <label htmlFor="myCustomSecurityQuestion">직접 질문 <b>필수</b></label>
                      <input id="myCustomSecurityQuestion" name="customSecurityQuestion" type="text"
                        value={hintForm.customSecurityQuestion} onChange={handleHintChange}
                        placeholder="20자 이내로 작성해주세요 :)" maxLength={20} required
                        aria-invalid={Boolean(hintErrors.customSecurityQuestion)} />
                      {hintErrors.customSecurityQuestion && <small className="my-error" role="alert">{hintErrors.customSecurityQuestion}</small>}
                    </div>
                  )}
                  <div className="my-field">
                    <label htmlFor="mySecurityAnswer">새 힌트 답변 <b>필수</b></label>
                    <input id="mySecurityAnswer" name="securityAnswer" type="text"
                      value={hintForm.securityAnswer} onChange={handleHintChange}
                      placeholder="답변을 입력해주세요" required aria-invalid={Boolean(hintErrors.securityAnswer)} />
                    {hintErrors.securityAnswer && <small className="my-error" role="alert">{hintErrors.securityAnswer}</small>}
                  </div>
                  <button className="my-submit" type="submit">힌트 질문 변경</button>
                </form>
              )}
            </section>

            <section className="my-section" aria-labelledby="my-usage-title">
              <div className="my-section-heading">
                <div><FileText size={19} /><h2 id="my-usage-title">OLIGO-K 이용 정보</h2></div>
              </div>
              <div className="my-usage-grid">
                <div><FileText size={18} /><span>저장된 기획안</span><strong>데이터 없음</strong></div>
                <div><MapPinned size={18} /><span>최근 분석지역</span><strong>-</strong></div>
                <div><CalendarDays size={18} /><span>최근 기획안 생성일</span><strong>-</strong></div>
              </div>
              <a className="my-outline-link" href="/saved-plans" onClick={handlePageLink('/saved-plans')}>
                저장된 기획안 보기
              </a>
            </section>
          </div>
        </div>

        <section className="my-account-actions" aria-label="계정 작업">
          <button className="my-logout-button" type="button" onClick={handleLogout}>
            <LogOut size={17} />로그아웃
          </button>
          <button className="my-danger-button" type="button" onClick={handleDeleteAccount}>
            <Trash2 size={15} />회원 탈퇴
          </button>
        </section>
      </section>
    </main>
  )
}
