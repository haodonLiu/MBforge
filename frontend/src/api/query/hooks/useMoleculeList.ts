/** React Query hook for molecule list (read-only). */

import { useQuery } from '@tanstack/react-query'
import { molAdminList } from '../../http/molecule_admin'
import { queryKeys } from '../keys'

/**
 * Paginated molecule list.
 *
 * Keeps the default stale time (30 s).  The MoleculeLibrary page
 * manages its own pagination state; this hook provides the base data
 * so consumer components can transition to React Query gradually.
 */
export function useMoleculeList(
  libraryRoot: string,
  limit = 100,
  offset = 0,
  sourceType?: string,
  status?: string,
) {
  return useQuery({
    queryKey: [...queryKeys.molecules.list(libraryRoot), { limit, offset, sourceType, status }],
    queryFn: () => molAdminList(libraryRoot, limit, offset, sourceType, status),
  })
}
