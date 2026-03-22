import React, { useEffect, useMemo } from 'react'
import { Box, Pagination, Text } from '@adminjs/design-system'
import { useRecords, useQueryParams } from 'adminjs'

function planLabel(record) {
  const ref = record.populated?.plan_id
  if (ref?.title) return ref.title
  if (ref?.params?.name) return ref.params.name
  if (typeof ref === 'string') return ref
  return record.params?.plan_id ? String(record.params.plan_id) : 'Unknown package'
}

/** Linked ``quotas`` row (limits + nested service). */
function quotaPayload(record) {
  const q = record.populated?.quota_id
  if (!q?.params) return null
  return q
}

function channelLabel(record) {
  const q = quotaPayload(record)
  if (q?.params?.name) return q.params.name
  const s = q?.populated?.service_id
  if (s?.title) return s.title
  if (s?.params?.name) return s.params.name
  return q?.params?.service_id ? String(q.params.service_id) : '—'
}

function formatDaily(n) {
  const v = Number(n)
  if (v === 0 || Number.isNaN(v)) return 'unlimited/day'
  return `${v}/day`
}

/**
 * Custom list: group plan_quotas links by package; read limits from linked Quota.
 */
const PlanQuotaList = (props) => {
  const { resource, setTag } = props
  const { records, loading, page, total, perPage } = useRecords(resource.id)
  const { storeParams } = useQueryParams()

  useEffect(() => {
    if (setTag) setTag(String(total))
  }, [setTag, total])

  const grouped = useMemo(() => {
    const map = new Map()
    for (const r of records) {
      const planId = r.params?.plan_id ?? r.id
      const label = planLabel(r)
      const key = String(planId)
      if (!map.has(key)) {
        map.set(key, { planId: key, planLabel: label, items: [] })
      }
      map.get(key).items.push(r)
    }
    const entries = [...map.values()]
    for (const g of entries) {
      g.items.sort((a, b) =>
        channelLabel(a).localeCompare(channelLabel(b), undefined, {
          sensitivity: 'base',
        })
      )
    }
    entries.sort((a, b) =>
      a.planLabel.localeCompare(b.planLabel, undefined, { sensitivity: 'base' })
    )
    return entries
  }, [records])

  const handlePaginationChange = (pageNumber) => {
    storeParams({ page: String(pageNumber) })
  }

  if (loading) {
    return (
      <Box variant="container" p="xl">
        <Text>Loading package quotas…</Text>
      </Box>
    )
  }

  return (
    <Box variant="container" p="default" data-css="plan-quota-grouped-list">
      {grouped.length === 0 ? (
        <Text color="grey60">
          No package quotas yet. Create **Quotas**, then link them here.
        </Text>
      ) : (
        grouped.map((group) => (
          <Box key={group.planId} mb="xxl">
            <Text fontSize="h3" fontWeight="bold" mb="default">
              📦 {group.planLabel}
            </Text>
            <Box as="ul" style={{ margin: 0, paddingLeft: 20 }}>
              {group.items.map((r) => {
                const q = quotaPayload(r)
                const daily = q?.params?.quota_daily
                const monthly = Number(q?.params?.quota_monthly)
                return (
                  <Box as="li" key={r.id} mb="sm">
                    <Text>
                      <strong>{channelLabel(r)}</strong>
                      {' → '}
                      {formatDaily(daily)}
                      {monthly > 0 && (
                        <span style={{ color: '#666' }}>
                          {' '}
                          / {monthly} monthly
                        </span>
                      )}
                    </Text>
                  </Box>
                )
              })}
            </Box>
          </Box>
        ))
      )}

      <Text mt="xl" textAlign="center">
        <Pagination
          page={page}
          perPage={perPage}
          total={total}
          onChange={handlePaginationChange}
        />
      </Text>
    </Box>
  )
}

export default PlanQuotaList
