import { describe, expect, it } from 'vitest';
import {
  formatBytes,
  formatPercent,
  predictionLabel,
  predictionLabelEn,
  predictionSymbol,
  validateImageFile,
} from '../utils/format';

function fileOf(name: string, type: string, size: number): File {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

describe('format helpers', () => {
  it('formats percentages with one decimal by default', () => {
    expect(formatPercent(0.9321)).toBe('93.2%');
    expect(formatPercent(0.5, 0)).toBe('50%');
  });

  it('formats byte sizes', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB');
  });

  it('maps prediction labels in both languages', () => {
    expect(predictionLabel('benign')).toBe('良性倾向');
    expect(predictionLabel('malignant')).toBe('恶性倾向');
    expect(predictionLabelEn('benign')).toBe('Benign');
    expect(predictionLabelEn('malignant')).toBe('Malignant');
  });

  it('provides a non-colour status symbol', () => {
    expect(predictionSymbol('benign')).not.toBe(predictionSymbol('malignant'));
  });
});

describe('validateImageFile', () => {
  it('accepts jpeg / png / webp / bmp', () => {
    for (const [name, type] of [
      ['a.jpg', 'image/jpeg'],
      ['b.png', 'image/png'],
      ['c.webp', 'image/webp'],
      ['d.bmp', 'image/bmp'],
    ]) {
      expect(validateImageFile(fileOf(name, type, 1024)).ok).toBe(true);
    }
  });

  it('rejects unsupported types', () => {
    const result = validateImageFile(fileOf('a.pdf', 'application/pdf', 1024));
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/仅支持/);
  });

  it('rejects files above the size limit', () => {
    const result = validateImageFile(fileOf('big.jpg', 'image/jpeg', 11 * 1024 * 1024));
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/10 MB/);
  });

  it('rejects empty files', () => {
    const result = validateImageFile(fileOf('empty.jpg', 'image/jpeg', 0));
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/文件为空/);
  });
});
