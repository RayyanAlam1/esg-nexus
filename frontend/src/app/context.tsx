import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { flattenEntities, useOrganization, useOrganizations } from '@/api/organizations';
import { useAuth } from '@/app/auth';
import type { EntityNode, OrganizationDetail, ReportingPeriod } from '@/api/types';
import { useLocalStorage } from '@/lib/utils';

export interface AppContextValue {
  org: OrganizationDetail | null;
  orgLoading: boolean;
  periods: ReportingPeriod[];
  entities: (EntityNode & { depth: number })[];
  period: string;
  entity: string;
  setPeriod: (p: string) => void;
  setEntity: (e: string) => void;
  /** Query-param scope for endpoints that accept period/entity. */
  scope: { period?: string; entity?: string };
  previousPeriod: string | null;
  /** True when the signed-in user may only see a subset of the entity tree. */
  entityScoped: boolean;
}

const AppContext = createContext<AppContextValue | null>(null);
const DEFAULT_PERIOD = 'FY2023';

export function AppContextProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const orgs = useOrganizations();
  const orgId = orgs.data && orgs.data.length > 0 ? orgs.data[0].id : null;
  const org = useOrganization(orgId);
  const [period, setPeriod] = useLocalStorage<string>('esgnexus.period', '');
  const [entity, setEntity] = useLocalStorage<string>('esgnexus.entity', '');

  const periods = useMemo(() => org.data?.periods ?? [], [org.data]);
  const allowedCodes = useMemo(() => new Set(user?.entity_codes ?? []), [user?.entity_codes]);
  const entityScoped = allowedCodes.size > 0;
  // A scoped user may only act on their own entities, so the selector must not offer others.
  // Offering the group entity to an entity-scoped user produces a 403 on every dashboard.
  const entities = useMemo(() => {
    const all = flattenEntities(org.data?.entities ?? []);
    return entityScoped ? all.filter((e) => allowedCodes.has(e.code)) : all;
  }, [org.data, entityScoped, allowedCodes]);

  // Defaults: FY2023 (or latest) and the first entity the user is allowed to see.
  useEffect(() => {
    if (periods.length && !periods.some((p) => p.code === period)) {
      const def = periods.find((p) => p.code === DEFAULT_PERIOD) ?? periods[periods.length - 1];
      setPeriod(def.code);
    }
    if (entities.length && !entities.some((e) => e.code === entity)) {
      const def = entities.find((e) => e.kind === 'group') ?? entities[0];
      setEntity(def.code);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [periods, entities]);

  const value = useMemo<AppContextValue>(() => {
    const idx = periods.findIndex((p) => p.code === period);
    return {
      org: org.data ?? null,
      orgLoading: orgs.isLoading || org.isLoading,
      periods,
      entities,
      period,
      entity,
      setPeriod,
      setEntity,
      scope: { period: period || undefined, entity: entity || undefined },
      previousPeriod: idx > 0 ? periods[idx - 1].code : null,
      entityScoped,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [org.data, orgs.isLoading, org.isLoading, periods, entities, period, entity, entityScoped]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useAppContext must be used inside AppContextProvider');
  return ctx;
}
