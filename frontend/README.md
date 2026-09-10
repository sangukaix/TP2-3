# OLIGO React + Vite frontend

`src/main.jsx`가 React 19 앱을 시작하고 `src/App.jsx`가 페이지를 지연 로딩합니다. 공개 경로와 과거 주소 별칭은 `src/routes.js`에서 관리합니다. 현재 화면 수가 적어 별도 Router 패키지를 설치하지 않으며, 알 수 없는 주소는 404 안내를 표시합니다.

개발 서버는 `/api`를 Backend `8100`, `/ai`를 AI Server `8112`로 프록시합니다. 배포에서는 같은 경로를 Nginx가 전달하고 모든 화면 경로는 `index.html`로 fallback해야 합니다.

검증 명령:

```powershell
npm test
npm run lint
npm run build
```
