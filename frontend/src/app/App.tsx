import { useState } from 'react'
import { NavLink, Route, Routes, useLocation, Link } from 'react-router-dom'
import { StatusProvider, useStatus } from './StatusContext'
import { Icon } from '../components/Icon'
import { UploadPage } from '../pages/UploadPage'
import { AnalysisPage } from '../pages/AnalysisPage'
import { RulesPage } from '../pages/RulesPage'
import { StatusPage } from '../pages/StatusPage'
import { DemoPage } from '../pages/DemoPage'
import { ReviewPage } from '../pages/ReviewPage'
import { isLocalReviewHost } from '../lib/review'
import { reviewText } from '../locales/review'
import { t } from '../locales/en'
function Shell() {
  const localReview = isLocalReviewHost()
  const [open, setOpen] = useState(false)
  const { status, error } = useStatus()
  const location = useLocation()
  const title =
    localReview || location.pathname.startsWith('/review')
      ? t.navReview
      : location.pathname.startsWith('/rules')
        ? t.navRules
        : location.pathname.startsWith('/status')
          ? t.navStatus
          : location.pathname.startsWith('/analysis')
            ? t.resultTitle
            : location.pathname.startsWith('/demo')
              ? t.synthetic
              : t.navAnalyze
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        {t.skip}
      </a>
      <aside className={`sidebar ${open ? 'is-open' : ''}`}>
        <Link
          to={localReview ? '/review' : '/'}
          className="wordmark"
          onClick={() => setOpen(false)}
        >
          <span>{t.brandName}</span>
          <small>{t.productName}</small>
        </Link>
        <div className="nav-caption">{t.workspace}</div>
        <nav aria-label={t.navLabel}>
          {localReview ? (
            <NavLink to="/review" onClick={() => setOpen(false)}>
              <Icon name="rules" />
              {t.navReview}
            </NavLink>
          ) : (
            <>
              <NavLink to="/" end onClick={() => setOpen(false)}>
                <Icon name="video" />
                {t.navAnalyze}
                <Icon name="chevron" size={14} />
              </NavLink>
              <NavLink to="/rules" onClick={() => setOpen(false)}>
                <Icon name="rules" />
                {t.navRules}
              </NavLink>
              <NavLink to="/status" onClick={() => setOpen(false)}>
                <Icon name="status" />
                {t.navStatus}
              </NavLink>
            </>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-icon">
            <Icon name="lock" size={18} />
          </div>
          <strong>{t.local}</strong>
          <p>{t.localDetail}</p>
          <span className="sidebar-prototype">{t.prototype}</span>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-title">
            <button
              className="icon-button menu-toggle"
              aria-label={t.navToggle}
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              <Icon name="menu" />
            </button>
            <div>
              <span>{title}</span>
              <small className="compact-prototype">{t.prototype}</small>
            </div>
          </div>
          <div className="header-meta">
            {localReview ? (
              <span className="readiness">
                <Icon name="lock" size={14} />
                {reviewText.local}
              </span>
            ) : (
              <Link to="/status" className={`readiness ${status?.ready ? 'is-ready' : ''}`}>
                <span className="status-dot" />
                {error
                  ? t.unavailable
                  : !status
                    ? t.readinessLoading
                    : status.ready
                      ? t.ready
                      : t.notReady}
              </Link>
            )}
            <span className="prototype-badge">{t.prototype}</span>
          </div>
        </header>
        <main id="main" className="main-content">
          <Routes>
            <Route path="/" element={localReview ? <ReviewPage /> : <UploadPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/analysis/:jobId" element={<AnalysisPage />} />
            <Route path="/rules" element={<RulesPage />} />
            <Route path="/status" element={<StatusPage />} />
            <Route path="/demo" element={<DemoPage />} />
            <Route
              path="*"
              element={
                <div className="empty-state">
                  <h1>{t.notFound}</h1>
                  <Link to="/">{t.back}</Link>
                </div>
              }
            />
          </Routes>
        </main>
        <footer className="app-footer">
          {t.footer}
          <span>{t.human}</span>
        </footer>
      </div>
    </div>
  )
}
export function App() {
  if (isLocalReviewHost()) return <Shell />
  return (
    <StatusProvider>
      <Shell />
    </StatusProvider>
  )
}
