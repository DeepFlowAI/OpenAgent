export type WeeklyServicePeriod = {
  day_of_week: number
  start: string
  end: string
}

export type ServiceHoursDateTimeRange = {
  name: string | null
  start_at: string
  end_at: string
}

export type ServiceHours = {
  id: number
  tenant_id: string
  name: string
  description: string | null
  timezone: string
  weekly_periods: WeeklyServicePeriod[]
  holidays: ServiceHoursDateTimeRange[]
  makeup_days: ServiceHoursDateTimeRange[]
  created_at: string
  updated_at: string
}

export type CreateServiceHoursPayload = {
  name: string
  description?: string | null
  timezone: string
  weekly_periods: WeeklyServicePeriod[]
  holidays: ServiceHoursDateTimeRange[]
  makeup_days: ServiceHoursDateTimeRange[]
}

export type UpdateServiceHoursPayload = Partial<CreateServiceHoursPayload>
