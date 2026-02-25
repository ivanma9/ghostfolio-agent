import type { ChatRequest, ChatResponse } from '../types'

export async function postChat(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })

  if (!response.ok) {
    throw new Error(`Chat API error: ${response.status} ${response.statusText}`)
  }

  return response.json() as Promise<ChatResponse>
}
