targetScope = 'resourceGroup'
param location string = resourceGroup().location
param namePrefix string = 'counterpress'
@description('First deploy false to create the workspace/table/DCR. Then true to associate and route logs. Preserve true on later deployments.')
param enableCollection bool = false

var workspaceName = '${namePrefix}-logs'
var ruleName = '${namePrefix}-ops-transform'
resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    // 25 MB/day guard; not a guaranteed billing cap. Emit only one numeric record/minute.
    workspaceCapping: { dailyQuotaGb: json('0.025') }
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
    defaultDataCollectionRuleResourceId: enableCollection ? resourceId('Microsoft.Insights/dataCollectionRules', ruleName) : null
  }
}
resource table 'Microsoft.OperationalInsights/workspaces/tables@2022-10-01' = {
  parent: workspace
  name: 'ContainerAppConsoleLogs'
  properties: { schema: { name: 'ContainerAppConsoleLogs' }, retentionInDays: 30, totalRetentionInDays: 30 }
}
resource transform 'Microsoft.Insights/dataCollectionRules@2023-03-11' = {
  name: ruleName
  location: location
  kind: 'WorkspaceTransforms'
  properties: {
    destinations: { logAnalytics: [{ name: 'ops', workspaceResourceId: workspace.id }] }
    dataFlows: [{
      streams: ['Microsoft-Table-ContainerAppConsoleLogs']
      destinations: ['ops']
      transformKql: loadTextContent('monitoring/transform.kql')
    }]
  }
  dependsOn: [table]
}
resource environment 'Microsoft.App/managedEnvironments@2025-07-01' existing = { name: '${namePrefix}-env' }
resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (enableCollection) {
  name: '${namePrefix}-ops'
  scope: environment
  properties: {
    workspaceId: workspace.id
    logAnalyticsDestinationType: 'Dedicated'
    logs: [{ category: 'ContainerAppConsoleLogs', enabled: true }]
  }
  dependsOn: [transform]
}
resource query 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: workspace
  name: 'counterpress-stream-operations'
  properties: {
    category: 'CounterPress'
    displayName: 'Streaming failures and delivery timing'
    query: loadTextContent('monitoring/operations.kql')
    version: 1
  }
}
