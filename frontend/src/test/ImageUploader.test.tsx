import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ImageUploader from '../components/ImageUploader';

function makeFile(name = 'lesion.jpg', type = 'image/jpeg', size = 1024): File {
  const file = new File(['x'.repeat(Math.min(size, 32))], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

/** `userEvent.upload` refuses files that violate the input's `accept` list,
 *  so a rejected-type test must inject the file directly. */
function injectFile(input: HTMLInputElement, file: File) {
  Object.defineProperty(input, 'files', { value: [file], configurable: true });
  fireEvent.change(input);
}

describe('ImageUploader', () => {
  it('renders the empty drop zone with an accessible select button', () => {
    render(
      <ImageUploader file={null} previewUrl={null} onSelect={vi.fn()} onClear={vi.fn()} />,
    );
    expect(screen.getByTestId('dropzone')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '选择图片' })).toBeEnabled();
    expect(screen.getByText(/拖拽图片到此处/)).toBeInTheDocument();
  });

  it('accepts a valid image through the file input', async () => {
    const onSelect = vi.fn();
    render(
      <ImageUploader file={null} previewUrl={null} onSelect={onSelect} onClear={vi.fn()} />,
    );
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const file = makeFile();
    await userEvent.upload(input, file);
    expect(onSelect).toHaveBeenCalledWith(file);
  });

  it('rejects a non-image file with a visible error', async () => {
    const onSelect = vi.fn();
    render(
      <ImageUploader file={null} previewUrl={null} onSelect={onSelect} onClear={vi.fn()} />,
    );
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    injectFile(input, makeFile('report.pdf', 'application/pdf'));
    expect(onSelect).not.toHaveBeenCalled();
    expect(await screen.findByRole('alert')).toHaveTextContent(/仅支持 JPG/);
  });

  it('rejects an oversized image', async () => {
    const onSelect = vi.fn();
    render(
      <ImageUploader file={null} previewUrl={null} onSelect={onSelect} onClear={vi.fn()} />,
    );
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    injectFile(input, makeFile('huge.jpg', 'image/jpeg', 11 * 1024 * 1024));
    expect(onSelect).not.toHaveBeenCalled();
    expect(await screen.findByRole('alert')).toHaveTextContent(/不能超过 10 MB/);
  });

  it('shows preview, file info and remove button when a file is selected', async () => {
    const onClear = vi.fn();
    const file = makeFile('mole.png', 'image/png', 2048);
    render(
      <ImageUploader
        file={file}
        previewUrl="blob:preview"
        onSelect={vi.fn()}
        onClear={onClear}
      />,
    );
    expect(screen.getByTestId('preview-image')).toHaveAttribute('src', 'blob:preview');
    expect(screen.getByTestId('file-name')).toHaveTextContent('mole.png');
    await userEvent.click(screen.getByTestId('remove-file-button'));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('surfaces a server-side error message', () => {
    render(
      <ImageUploader
        file={null}
        previewUrl={null}
        onSelect={vi.fn()}
        onClear={vi.fn()}
        error="上传文件不是有效图片"
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('上传文件不是有效图片');
  });

  it('disables interaction while a detection is running', () => {
    render(
      <ImageUploader
        file={null}
        previewUrl={null}
        onSelect={vi.fn()}
        onClear={vi.fn()}
        disabled
      />,
    );
    expect(screen.getByTestId('select-file-button')).toBeDisabled();
  });
});
