targetScope = 'resourceGroup'

param budgetName string = 'counterpress-hackathon'
@minValue(1)
param amount int
@description('First day of the current quarter, in ISO 8601 format.')
param startDate string
@description('Explicit trial-end boundary; alerts do not stop resources.')
param endDate string
@secure()
param contactEmail string

resource budget 'Microsoft.Consumption/budgets@2024-08-01' = {
  name: budgetName
  properties: {
    category: 'Cost'
    amount: amount
    // One envelope across the trial's calendar-month boundary.
    timeGrain: 'Quarterly'
    timePeriod: { startDate: startDate, endDate: endDate }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: [contactEmail]
      }
      actual75: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 75
        thresholdType: 'Actual'
        contactEmails: [contactEmail]
      }
      actual90: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 90
        thresholdType: 'Actual'
        contactEmails: [contactEmail]
      }
      actual100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: [contactEmail]
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: [contactEmail]
      }
    }
  }
}
