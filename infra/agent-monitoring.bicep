targetScope = 'resourceGroup'

param location string = resourceGroup().location
param namePrefix string = 'counterpress'
param foundryAccountName string = 'counterpress-dev-01'
param foundryProjectName string = 'CounterPress'

// Reuse the bounded workspace; this template does not change its retention/cap.
resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: '${namePrefix}-logs'
}
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: '${namePrefix}-history'
}
resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: '${namePrefix}-deploy'
}
resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: account
  name: foundryProjectName
}
resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-agents'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    IngestionMode: 'LogAnalytics'
    RetentionInDays: 30
    DisableLocalAuth: true
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}
resource publisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(insights.id, identity.id, '3913510d-42f4-4e42-8a64-420c390055eb')
  scope: insights
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '3913510d-42f4-4e42-8a64-420c390055eb')
  }
}
// The guarded OIDC image release resolves these two metadata resources only.
// No listSecrets action, data-plane reader, Contributor or role-write permission.
resource deploymentInsightsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(insights.id, deployIdentity.id, 'Reader')
  scope: insights
  properties: {
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  }
}
resource deploymentIdentityReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(identity.id, deployIdentity.id, 'Reader')
  scope: identity
  properties: {
    principalId: deployIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'acdd72a7-3385-48ef-bd42-f606fba81ae7')
  }
}
// ApiKey here is the Foundry connection schema, not permission to ingest with
// local keys: DisableLocalAuth above requires Entra identity for actual export.
resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'footie-agent-monitoring'
  properties: {
    category: 'AppInsights'
    authType: 'ApiKey'
    target: insights.properties.ConnectionString
    credentials: { key: insights.properties.ConnectionString }
    metadata: { ApiType: 'Azure', ResourceId: insights.id }
    isSharedToAll: false
  }
}

// No connection strings, identifiers or secrets in deployment outputs.
output applicationInsightsName string = insights.name
output foundryConnectionName string = connection.name
