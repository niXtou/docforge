import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import * as client from './api/client'
import type {
  Schema,
  ExtractionJobResponse,
  ExtractionJobSummary,
  ExtractionResult,
} from './types'

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
  model_used: 'google/gemini-3.1-flash-lite',
  processing_time_ms: 800,
  chunks_processed: 1,
  error_message: null,
  validation_errors: [],
  evidence: {
    invoice_number: { quote: 'Invoice INV-001 dated', method: 'verbatim', supported: true },
    total_amount: { quote: '', method: 'unverified', supported: true },
  },
}

const mockJobs: ExtractionJobSummary[] = [
  {
    job_id: 'test-job-123',
    status: 'completed',
    schema_name: 'Invoice',
    original_filename: 'old-invoice.pdf',
    model_used: 'google/gemini-3.1-flash-lite',
    created_at: '2026-01-01T00:00:00',
    completed_at: '2026-01-01T00:00:01',
    processing_time_ms: 800,
    retries_used: 1,
    validation_passed: true,
  },
  {
    job_id: 'test-job-456',
    status: 'processing',
    schema_name: 'Invoice',
    original_filename: 'in-flight.pdf',
    model_used: 'google/gemini-3.1-flash-lite',
    created_at: '2026-01-01T00:00:00',
    completed_at: null,
    processing_time_ms: null,
    retries_used: 0,
    validation_passed: null,
  },
]

beforeEach(() => {
  vi.spyOn(client, 'listSchemas').mockResolvedValue(mockSchemas)
  vi.spyOn(client, 'listJobs').mockResolvedValue([])
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

  it('reopens a finished job from recent jobs', async () => {
    const user = userEvent.setup()
    vi.spyOn(client, 'listJobs').mockResolvedValue(mockJobs)
    render(<App />)

    const finished = await screen.findByRole('button', { name: /old-invoice\.pdf/ })
    // In-flight jobs are listed but not clickable.
    expect(screen.getByText('in-flight.pdf')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /in-flight\.pdf/ })).toBeNull()

    await user.click(finished)

    await waitFor(() => expect(client.getResult).toHaveBeenCalledWith('test-job-123'))
    expect(await screen.findByText('Extraction results')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('old-invoice.pdf')
    // Table is the default view and carries the evidence quote.
    expect(screen.getByText('Invoice INV-001 dated')).toBeInTheDocument()
    expect(screen.getByText('1 of 2 values grounded')).toBeInTheDocument()
  })
})
