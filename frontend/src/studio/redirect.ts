import { broadcastResponseToMainFrame } from '@azure/msal-browser/redirect-bridge'
void broadcastResponseToMainFrame().catch(() => {
  document.body.textContent = 'Sign-in could not finish. Close this window and try again in Studio.'
})
