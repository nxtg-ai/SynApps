/**
 * SchemaForm -- renders a dynamic form from a JSON Schema object.
 *
 * Supported field types:
 *   - string   -> text input
 *   - number / integer -> number input
 *   - boolean  -> checkbox
 *   - array (of strings) -> comma-separated text input
 *   - object   -> nested section (one level of recursion)
 *   - unknown  -> text input fallback
 */
import React, { useCallback } from 'react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SchemaFormProps {
  schema: Record<string, unknown>;
  value: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
  disabled?: boolean;
}

interface PropertySchema {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  items?: Record<string, unknown>;
  properties?: Record<string, Record<string, unknown>>;
  required?: string[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Convert a camelCase or snake_case key into a human-readable label. */
function prettifyKey(key: string): string {
  return key
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function getLabel(key: string, prop: PropertySchema): string {
  return prop.title ?? prettifyKey(key);
}

// ---------------------------------------------------------------------------
// Field renderers
// ---------------------------------------------------------------------------

interface FieldProps {
  fieldKey: string;
  prop: PropertySchema;
  value: unknown;
  required: boolean;
  disabled: boolean;
  onFieldChange: (key: string, value: unknown) => void;
}

const SchemaField: React.FC<FieldProps> = ({
  fieldKey,
  prop,
  value,
  required,
  disabled,
  onFieldChange,
}) => {
  const label = getLabel(fieldKey, prop);
  const fieldType = prop.type ?? 'string';
  const fieldId = `schema-field-${fieldKey}`;

  if (fieldType === 'object' && prop.properties) {
    return (
      <fieldset className="mb-4 rounded border border-slate-700 p-3">
        <legend className="px-1 text-sm font-semibold text-slate-200">{label}</legend>
        {Object.entries(prop.properties).map(([nestedKey, nestedProp]) => {
          const nestedValue = (value as Record<string, unknown> | undefined)?.[nestedKey] ?? '';
          return (
            <SchemaField
              key={nestedKey}
              fieldKey={`${fieldKey}.${nestedKey}`}
              prop={nestedProp as PropertySchema}
              value={nestedValue}
              required={false}
              disabled={disabled}
              onFieldChange={(compoundKey, val) => {
                const parentObj = (value as Record<string, unknown>) ?? {};
                onFieldChange(fieldKey, { ...parentObj, [nestedKey]: val });
              }}
            />
          );
        })}
      </fieldset>
    );
  }

  if (fieldType === 'boolean') {
    const checked = typeof value === 'boolean' ? value : false;
    return (
      <div className="mb-3 flex items-center gap-2">
        <input
          id={fieldId}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onFieldChange(fieldKey, e.target.checked)}
          className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-indigo-500"
        />
        <label htmlFor={fieldId} className="text-sm text-slate-300">
          {label}
          {required && <span className="ml-0.5 text-red-400">*</span>}
        </label>
        {prop.description && (
          <span className="text-xs text-slate-500">{prop.description}</span>
        )}
      </div>
    );
  }

  const inputType =
    fieldType === 'number' || fieldType === 'integer' ? 'number' : 'text';

  const displayValue =
    fieldType === 'array'
      ? Array.isArray(value)
        ? (value as string[]).join(', ')
        : typeof value === 'string'
          ? value
          : ''
      : value ?? '';

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    if (fieldType === 'number' || fieldType === 'integer') {
      onFieldChange(fieldKey, raw === '' ? '' : Number(raw));
    } else if (fieldType === 'array') {
      const items = raw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      onFieldChange(fieldKey, items);
    } else {
      onFieldChange(fieldKey, raw);
    }
  };

  return (
    <div className="mb-3">
      <label htmlFor={fieldId} className="mb-1 block text-sm text-slate-300">
        {label}
        {required && <span className="ml-0.5 text-red-400">*</span>}
      </label>
      <input
        id={fieldId}
        type={inputType}
        value={String(displayValue)}
        disabled={disabled}
        onChange={handleChange}
        className="w-full rounded border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100 disabled:opacity-50"
      />
      {prop.description && (
        <p className="mt-0.5 text-xs text-slate-500">{prop.description}</p>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const SchemaForm: React.FC<SchemaFormProps> = ({ schema, value, onChange, disabled = false }) => {
  const properties = (schema.properties ?? {}) as Record<string, PropertySchema>;
  const requiredFields = (schema.required ?? []) as string[];

  const handleFieldChange = useCallback(
    (key: string, fieldValue: unknown) => {
      onChange({ ...value, [key]: fieldValue });
    },
    [value, onChange],
  );

  return (
    <div data-testid="schema-form">
      {Object.entries(properties).map(([key, prop]) => {
        const fieldValue = value[key] ?? prop.default ?? (prop.type === 'boolean' ? false : '');
        const isRequired = requiredFields.includes(key);

        return (
          <SchemaField
            key={key}
            fieldKey={key}
            prop={prop}
            value={fieldValue}
            required={isRequired}
            disabled={disabled}
            onFieldChange={handleFieldChange}
          />
        );
      })}
    </div>
  );
};

export default SchemaForm;
