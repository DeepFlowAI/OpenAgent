export type FeedbackRating = 'like' | 'dislike'

export type SubmitStepFeedbackPayload = {
  rating: FeedbackRating
  comment?: string | null
}

export type StepFeedbackResponse = {
  step_id: number
  feedback_rating: FeedbackRating
  feedback_comment: string | null
  feedback_updated_at: string
}
