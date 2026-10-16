targetScope = 'resourceGroup'
param location string = resourceGroup().location
param namePrefix string = 'counterpress'
resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = { name: '${namePrefix}-logs' }
resource streamIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = { name: '${namePrefix}-stream' }
var columns = loadJsonContent('monitoring/columns.json')
resource table 'Microsoft.OperationalInsights/workspaces/tables@2022-10-01' = {
  parent: workspace
  name: 'CounterPressOperations_CL'
  properties: {
    schema: { name: 'CounterPressOperations_CL', columns: columns }
    retentionInDays: 30
    totalRetentionInDays: 30
  }
}
resource rule 'Microsoft.Insights/dataCollectionRules@2023-03-11' = {
  name: '${namePrefix}-ops-ingest'
  location: location
  kind: 'Direct'
  properties: {
    streamDeclarations: { 'Custom-CounterPressOperations': { columns: columns } }
    destinations: { logAnalytics: [{ name: 'ops', workspaceResourceId: workspace.id }] }
    dataFlows: [{
      streams: ['Custom-CounterPressOperations']
      destinations: ['ops']
      transformKql: 'source'
      outputStream: 'Custom-CounterPressOperations_CL'
    }]
  }
  dependsOn: [table]
}
resource publisherRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(rule.id, streamIdentity.id, 'metrics-publisher')
  scope: rule
  properties: {
    principalId: streamIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '3913510d-42f4-4e42-8a64-420c390055eb')
  }
}
resource query 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: workspace
  name: 'counterpress-direct-operations'
  properties: {
    category: 'CounterPress'
    displayName: 'Acknowledged streaming operations'
    query: loadTextContent('monitoring/direct-operations.kql')
    version: 1
  }
}
