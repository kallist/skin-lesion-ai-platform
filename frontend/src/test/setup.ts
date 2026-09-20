import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

// jsdom does not implement these APIs that the app relies on.
if (!URL.createObjectURL) {
  Object.defineProperty(URL, 'createObjectURL', { writable: true, value: vi.fn(() => 'blob:mock') });
}
if (!URL.revokeObjectURL) {
  Object.defineProperty(URL, 'revokeObjectURL', { writable: true, value: vi.fn() });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
