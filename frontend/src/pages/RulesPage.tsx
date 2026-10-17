import { useEffect, useState } from 'react'
import { getRules } from '../lib/api'
import type { Rule } from '../lib/types'
import { readable } from '../lib/format'
import { RuleSource } from '../components/RuleSource'
import { Icon } from '../components/Icon'
import { t } from '../locales/en'
export function RulesPage() {
  const [rules, setRules] = useState<Rule[] | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let disposed = false
    getRules()
      .then((data) => {
        if (!disposed) {
          setRules(data.rules)
          setError('')
        }
      })
      .catch((e) => {
        if (!disposed) setError(e.message)
      })
    return () => {
      disposed = true
    }
  }, [attempt])
  const matches = rules?.filter((rule) =>
    [rule.title, rule.document_title, rule.observed_condition, rule.id]
      .join(' ')
      .toLowerCase()
      .includes(query.toLowerCase()),
  )
  return (
    <div className="page">
      <div className="page-heading">
        <p className="eyebrow">{t.rulesEyebrow}</p>
        <h1>{t.rulesTitle}</h1>
        <p className="lede">{t.rulesDescription}</p>
      </div>
      <div className="search-field">
        <Icon name="search" />
        <input
          aria-label={t.searchRules}
          placeholder={t.searchRules}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {error ? (
        <div role="alert" className="error-message">
          {error}
          <button className="text-button" onClick={() => setAttempt((a) => a + 1)}>
            {t.retry}
          </button>
        </div>
      ) : !rules ? (
        <p role="status">{t.loading}</p>
      ) : !matches?.length ? (
        <section className="card empty-state">
          <div className="empty-icon">
            <Icon name="rules" size={30} />
          </div>
          <h2>{rules.length ? t.noMatches : t.rulesEmpty}</h2>
          <p>{!rules.length && t.rulesEmptyBody}</p>
        </section>
      ) : (
        <div className="rules-grid">
          {matches.map((rule) => (
            <article className="card registry-rule" key={rule.id}>
              <div className="section-title">
                <h2>{rule.title}</h2>
                <span
                  className={`rule-status ${!rule.enabled ? 'disabled' : rule.verification_status}`}
                >
                  {!rule.enabled ? t.status.disabled : t.status[rule.verification_status]}
                </span>
              </div>
              <p className="rule-id">
                {rule.id} · {t.version} {rule.version}
              </p>
              <h3>{t.visibleCondition}</h3>
              <p>{rule.observed_condition}</p>
              <h3>{t.requiredContext}</h3>
              <p>{readable(rule.required_context)}</p>
              <h3>{t.ruleSource}</h3>
              <RuleSource rule={rule} />
              <h3>{t.limitations}</h3>
              <ul>
                {rule.limitations.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
      <p className="page-note">{t.rulesReadOnly}</p>
    </div>
  )
}
