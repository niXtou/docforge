import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import * as client from './api/client'
import type { Schema, ExtractionJobResponse, ExtractionResult } from './types'

// Minimal mock schemas
const mockSchemas: Schema[] = [
  { id: 1, name: 'Invoice', description: 'Test', json_schema: {}, is_builtin: true, created_at: '' },
]

const mockJobResponse: ExtractionJobResponse = {
  job_id: 'test-job-123',
  status: 'pending',
  schema_name: 'Invoice',
  created_at: '',
}

const mockResult: ExtractionResult = {
  job_id: 'test-job-123',
  status: 'completed',
  data: { invoice_number: 'INV-001', total_amount: 100 },
  validation_passed: true,
  retries_used: 0,
  model_used: 'google/gemini-2.0-flash',
  processing_time_ms: 800,
  chunks_processed: 1,
}

beforeEach(() => {
  vi.spyOn(client, 'listSchemas').mockResolvedValue(mockSchemas)
  vi.spyOn(client, 'uploadDocument').mockResolvedValue(mockJobResponse)
  vi.spyOn(client, 'getResult').mockResolvedValue(mockResult)
  vi.spyOn(client, 'streamUrl').mockReturnValue('/api/extract/test-job-123/stream')
})

describe('App wizard flow', () => {
  it('renders schema selector on load', async () => {
    render(<App />)
    await waitFor(() => expect(screen.getByText('Invoice')).toBeInTheDocument())
  })

  it('extract button is disabled until schema and file are selected', async () => {
    render(<App />)
    await waitFor(() => screen.getByText('Invoice'))
    expect(screen.getByRole('button', { name: /extract/i })).toBeDisabled()
  })

  it('submits form and transitions to streaming step', async () => {
    const user = userEvent.setup()
    render(<App />)

    // Wait for schemas to load
    await waitFor(() => screen.getByText('Invoice'))

    // Select schema
    const select = screen.getByRole('combobox')
    await user.selectOptions(select, '1')

    // Upload a file
    const file = new File(['pdf content'], 'test.pdf', { type: 'application/pdf' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    // Click Extract
    const extractBtn = screen.getByRole('button', { name: /extract/i })
    await waitFor(() => expect(extractBtn).not.toBeDisabled())
    await user.click(extractBtn)

    // Should transition to streaming step
    await waitFor(() => {
      expect(client.uploadDocument).toHaveBeenCalledOnce()
    })
  })
})
