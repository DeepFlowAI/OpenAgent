import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from '@/service/base'
import type {
  CreateKnowledgeBaseQaDirectoryPayload,
  KnowledgeBaseQaDirectory,
  KnowledgeBaseQaDirectoryList,
  UpdateKnowledgeBaseQaDirectoryPayload,
} from '@/models/knowledge-base-qa-directory'

const NS = 'knowledge-base-qa-directories'

export const knowledgeBaseQaDirectoryKeys = {
  all: [NS] as const,
  list: (kbId: number) => [NS, 'list', kbId] as const,
}

export const useKnowledgeBaseQaDirectories = (kbId: number) =>
  useQuery({
    queryKey: knowledgeBaseQaDirectoryKeys.list(kbId),
    queryFn: () =>
      get<KnowledgeBaseQaDirectoryList>(
        `v1/knowledge-bases/${kbId}/qa-directories`,
      ),
    enabled: !!kbId,
  })

function useInvalidateDirectories() {
  const qc = useQueryClient()
  return (kbId: number) => {
    void qc.invalidateQueries({ queryKey: knowledgeBaseQaDirectoryKeys.list(kbId) })
    void qc.invalidateQueries({ queryKey: ['knowledge-base-qas', 'list'] })
  }
}

export const useCreateKnowledgeBaseQaDirectory = () => {
  const invalidate = useInvalidateDirectories()
  return useMutation({
    mutationFn: ({
      kbId,
      data,
    }: {
      kbId: number
      data: CreateKnowledgeBaseQaDirectoryPayload
    }) =>
      post<KnowledgeBaseQaDirectory>(
        `v1/knowledge-bases/${kbId}/qa-directories`,
        { json: data },
      ),
    onSuccess: (item) => invalidate(item.knowledge_base_id),
  })
}

export const useUpdateKnowledgeBaseQaDirectory = () => {
  const invalidate = useInvalidateDirectories()
  return useMutation({
    mutationFn: ({
      kbId,
      directoryId,
      data,
    }: {
      kbId: number
      directoryId: number
      data: UpdateKnowledgeBaseQaDirectoryPayload
    }) =>
      put<KnowledgeBaseQaDirectory>(
        `v1/knowledge-bases/${kbId}/qa-directories/${directoryId}`,
        { json: data },
      ),
    onSuccess: (item) => invalidate(item.knowledge_base_id),
  })
}

export const useDeleteKnowledgeBaseQaDirectory = () => {
  const invalidate = useInvalidateDirectories()
  return useMutation({
    mutationFn: ({ kbId, directoryId }: { kbId: number; directoryId: number }) =>
      del(`v1/knowledge-bases/${kbId}/qa-directories/${directoryId}`),
    onSuccess: (_, values) => invalidate(values.kbId),
  })
}
