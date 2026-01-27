import api from './index'

export async function sendCommand(payload){
  // POST /api/v1/commands
  return api.post('/v1/commands', payload)
}

export async function listCommands(params){
  // GET /api/v1/commands
  return api.get('/v1/commands', { params })
}
