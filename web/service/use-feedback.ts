import { post } from '@/service/base'
import type {
  StepFeedbackResponse,
  SubmitStepFeedbackPayload,
} from '@/models/feedback'

export const submitPublicStepFeedback = (
  channelToken: string,
  stepId: number,
  data: SubmitStepFeedbackPayload,
) =>
  post<StepFeedbackResponse>(
    `v1/public/channels/${channelToken}/steps/${stepId}/feedback`,
    { json: data },
  )
