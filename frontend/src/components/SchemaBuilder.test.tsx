import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import * as client from '../api/client'
import type { Schema } from '../types'
import { SchemaBuilder } from './SchemaBuilder'

const created: Schema = {
  id: 42,
  name: 'Purchase Order',
  description: 'PO fields',
  json_schema: {},
  is_builtin: false,
  created_at: '',
}

afterEach(() => vi.restoreAllMocks())

describe('SchemaBuilder', () => {
  it('previews the fields as JSON Schema and submits them', async () => {
    const user = userEvent.setup()
    const createSpy = vi.spyOn(client, 'createSchema').mockResolvedValue(created)
    const onCreated = vi.fn()
    render(<SchemaBuilder onClose={vi.fn()} onCreated={onCreated} />)

    const createBtn = screen.getByRole('button', { name: 'Create' })
    expect(createBtn).toBeDisabled()

    await user.type(screen.getByPlaceholderText('Purchase order'), 'Purchase Order')
    await user.type(screen.getByPlaceholderText('What this schema extracts'), 'PO fields')
    await user.selectOptions(screen.getByRole('combobox', { name: /document type/i }), 'invoice')

    // First field: required string.
    await user.type(screen.getByLabelText('Field 1 name'), 'po_number')
    await user.type(screen.getByLabelText('Field 1 description'), 'The PO number')
    await user.click(screen.getByLabelText('Field 1 required'))

    // Second field: string array.
    await user.click(screen.getByRole('button', { name: /add field/i }))
    await user.type(screen.getByLabelText('Field 2 name'), 'line_items')
    await user.selectOptions(screen.getByLabelText('Field 2 type'), 'string[]')

    const preview = screen.getByTestId('schema-preview')
    expect(preview).toHaveTextContent('"po_number"')
    expect(preview).toHaveTextContent('"line_items"')
    expect(preview).toHaveTextContent('"x-doc-type": "invoice"')

    expect(createBtn).not.toBeDisabled()
    await user.click(createBtn)

    await waitFor(() => expect(createSpy).toHaveBeenCalledOnce())
    expect(createSpy).toHaveBeenCalledWith({
      name: 'Purchase Order',
      description: 'PO fields',
      json_schema: {
        type: 'object',
        'x-doc-type': 'invoice',
        properties: {
          po_number: { type: 'string', description: 'The PO number' },
          line_items: { type: 'array', items: { type: 'string' } },
        },
        required: ['po_number'],
      },
    })
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created))
  })

  it('omits x-doc-type for generic schemas and rejects invalid field names', async () => {
    const user = userEvent.setup()
    const createSpy = vi.spyOn(client, 'createSchema').mockResolvedValue(created)
    render(<SchemaBuilder onClose={vi.fn()} onCreated={vi.fn()} />)

    await user.type(screen.getByPlaceholderText('Purchase order'), 'Generic')
    await user.type(screen.getByLabelText('Field 1 name'), '1bad-name')
    expect(screen.getByTestId('schema-preview')).not.toHaveTextContent('x-doc-type')

    await user.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('"1bad-name" is invalid')
    expect(createSpy).not.toHaveBeenCalled()
  })

  it('shows the API error inline', async () => {
    const user = userEvent.setup()
    vi.spyOn(client, 'createSchema').mockRejectedValue(new Error('Schema name already exists'))
    render(<SchemaBuilder onClose={vi.fn()} onCreated={vi.fn()} />)

    await user.type(screen.getByPlaceholderText('Purchase order'), 'Invoice')
    await user.type(screen.getByLabelText('Field 1 name'), 'total')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Schema name already exists')
  })
})
