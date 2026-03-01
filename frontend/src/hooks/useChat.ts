import { useState, useRef, useCallback } from 'react'
import { v4 as uuidv4 } from 'uuid'
import { postChat, ChatError } from '../api/chat'
import type { ChatMessage } from '../types'

const SESSION_KEY = 'ghostfolio-session-id'

function getOrCreateSessionId(): string {
  const stored = localStorage.getItem(SESSION_KEY)
  if (stored) return stored
  const id = uuidv4()
  localStorage.setItem(SESSION_KEY, id)
  return id
}

interface UseChatOptions {
  onToolCall?: (toolCalls: string[]) => void
}

interface UseChatReturn {
  messages: ChatMessage[]
  isLoading: boolean
  sendMessage: (text: string, model?: string, paperTrading?: boolean) => Promise<void>
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { onToolCall } = options
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const sessionIdRef = useRef<string>(getOrCreateSessionId())

  const sendMessage = useCallback(
    async (text: string, model?: string, paperTrading?: boolean) => {
      if (!text.trim() || isLoading) return

      const userMessage: ChatMessage = {
        id: uuidv4(),
        role: 'user',
        content: text.trim(),
        toolCalls: [],
        timestamp: new Date(),
      }

      setMessages((prev) => [...prev, userMessage])
      setIsLoading(true)

      try {
        const data = await postChat({
          message: text.trim(),
          session_id: sessionIdRef.current,
          model,
          paper_trading: paperTrading,
        })

        const assistantMessage: ChatMessage = {
          id: uuidv4(),
          role: 'assistant',
          content: data.response,
          toolCalls: data.tool_calls ?? [],
          timestamp: new Date(),
          confidence: data.confidence,
          verificationIssues: data.verification_issues,
        }

        setMessages((prev) => [...prev, assistantMessage])

        if (data.tool_calls && data.tool_calls.length > 0) {
          onToolCall?.(data.tool_calls)
        }
      } catch (error) {
        const content = error instanceof ChatError
          ? error.message
          : 'Sorry, something went wrong. Please try again.'
        const errorMessage: ChatMessage = {
          id: uuidv4(),
          role: 'assistant',
          content,
          toolCalls: [],
          timestamp: new Date(),
          isError: true,
        }
        setMessages((prev) => [...prev, errorMessage])
        console.error('Chat error:', error)
      } finally {
        setIsLoading(false)
      }
    },
    [isLoading, onToolCall]
  )

  return { messages, isLoading, sendMessage }
}
