import type { Rule } from '../lib/types'
import { t } from '../locales/en'
import { Icon } from './Icon'
export function RuleSource({ rule }: { rule: Rule | null }) {
  if (!rule)
    return (
      <div className="rule-source">
        <p>{t.noVerifiedMapping}</p>
      </div>
    )
  const safeUrl = rule.source_url && /^https?:\/\//.test(rule.source_url) ? rule.source_url : null
  return (
    <div className="rule-source">
      <div className="source-title">
        <Icon name="rules" />
        <div>
          <strong>{rule.document_title}</strong>
          <span>{rule.source_type}</span>
        </div>
      </div>
      <dl>
        <div>
          <dt>{t.section}</dt>
          <dd>{rule.section_or_paragraph || t.noSection}</dd>
        </div>
        <div>
          <dt>{t.excerpt}</dt>
          <dd className="excerpt">{rule.relevant_excerpt}</dd>
        </div>
        <div>
          <dt>{t.recordedInterpretation}</dt>
          <dd>{rule.interpretation}</dd>
        </div>
      </dl>
      {safeUrl && (
        <a href={safeUrl} target="_blank" rel="noopener noreferrer" className="source-link">
          {t.openSource}
          <Icon name="external" size={15} />
        </a>
      )}
    </div>
  )
}
