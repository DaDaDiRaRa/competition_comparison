import { createContext, useContext, useEffect, useState } from 'react'
import { getMeta } from '../api/client'

const MetaContext = createContext(null)

export function MetaProvider({ children }) {
  const [meta, setMeta] = useState(null)

  useEffect(() => {
    getMeta().then(setMeta).catch(() => {})
  }, [])

  return <MetaContext.Provider value={meta}>{children}</MetaContext.Provider>
}

export function useMeta() {
  const meta = useContext(MetaContext)

  const facilityLabel = (key) =>
    meta?.facility_types?.find(f => f.key === key)?.label_ko ?? key

  const facilityGroup = (key) =>
    meta?.facility_types?.find(f => f.key === key)?.group ?? 'general'

  const facilityTypes = meta?.facility_types ?? []

  const pageTypeLabel = (key) => meta?.page_types?.[key] ?? key

  const axesFor = (facility_type) => {
    const group = facilityGroup(facility_type)
    return meta?.axes_by_group?.[group] ?? {}
  }

  const axisLabel = (facility_type, axis_key) => {
    const axes = axesFor(facility_type)
    return axes[axis_key]?.label_ko ?? axis_key
  }

  return {
    ready: !!meta,
    facilityLabel,
    facilityGroup,
    facilityTypes,
    pageTypeLabel,
    axesFor,
    axisLabel,
  }
}
