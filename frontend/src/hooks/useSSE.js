import {
    useEffect,
    useRef
} from 'react'

/**
 * Custom hook for Server-Sent Events (SSE)
 * @param {string} url - SSE endpoint URL
 * @param {function} onMessage - Callback function when message is received
 * @param {function} onError - Optional error callback
 */
export function useSSE(url, onMessage, onError) {
    const eventSourceRef = useRef(null)
    const onMessageRef = useRef(onMessage)
    const onErrorRef = useRef(onError)

    // Update refs when callbacks change
    useEffect(() => {
        onMessageRef.current = onMessage
        onErrorRef.current = onError
    }, [onMessage, onError])

    useEffect(() => {
        // Create EventSource connection
        console.log('Creating SSE connection to:', url)
        const eventSource = new EventSource(url)
        eventSourceRef.current = eventSource

        // Log connection state changes
        eventSource.onopen = () => {
            console.log('SSE connection opened, readyState:', eventSource.readyState)
        }

        // Handle messages
        eventSource.onmessage = (event) => {
            try {
                console.log('SSE raw message received:', event.data)
                const data = JSON.parse(event.data)
                console.log('SSE parsed data:', data)
                if (onMessageRef.current) {
                    onMessageRef.current(data)
                }
            } catch (error) {
                console.error('Error parsing SSE message:', error, 'Raw data:', event.data)
                if (onErrorRef.current) {
                    onErrorRef.current(error)
                }
            }
        }

        // Handle errors
        eventSource.onerror = (error) => {
            console.error('SSE connection error:', error)
            console.error('SSE readyState:', eventSource.readyState)
            // EventSource readyState: 0=CONNECTING, 1=OPEN, 2=CLOSED
            if (onErrorRef.current) {
                onErrorRef.current(error)
            }
            // EventSource will automatically try to reconnect
        }

        // Cleanup on unmount
        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close()
                eventSourceRef.current = null
            }
        }
    }, [url])

    return eventSourceRef.current
}