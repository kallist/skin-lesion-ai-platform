import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import LoginPage from '../pages/LoginPage';
import HistoryPage from '../pages/HistoryPage';
import { ToastProvider } from '../hooks/useToasts';
import { AuthProvider } from '../hooks/useAuth';
import { api, ApiError } from '../api/client';

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {
    ...actual,
    api: {
      session: vi.fn(),
      login: vi.fn(),
      logout: vi.fn(),
      listDetections: vi.fn(),
      exportCsv: vi.fn(),
      fetchDetectionImage: vi.fn(),
    },
  };
});

function renderWithProviders(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <ToastProvider>
        <AuthProvider>{ui}</AuthProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
}

const mockedApi = api as unknown as {
  session: ReturnType<typeof vi.fn>;
  login: ReturnType<typeof vi.fn>;
  listDetections: ReturnType<typeof vi.fn>;
  fetchDetectionImage: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  mockedApi.session.mockRejectedValue(new ApiError(401, 'UNAUTHENTICATED', '请先登录'));
  mockedApi.fetchDetectionImage.mockResolvedValue(new Blob(['x'], { type: 'image/png' }));
});

describe('LoginPage', () => {
  it('submits credentials and reports backend errors', async () => {
    mockedApi.login.mockRejectedValue(new ApiError(401, 'UNAUTHENTICATED', '邮箱/用户名或密码错误'));
    renderWithProviders(<LoginPage />);

    await userEvent.type(screen.getByTestId('login-identifier'), 'tester');
    await userEvent.type(screen.getByTestId('login-password'), 'wrongpass1');
    await userEvent.click(screen.getByTestId('login-submit'));

    expect(await screen.findByTestId('login-error')).toHaveTextContent('邮箱/用户名或密码错误');
  });

  it('has labelled, keyboard-reachable inputs', () => {
    renderWithProviders(<LoginPage />);
    expect(screen.getByLabelText('邮箱或用户名')).toBeInTheDocument();
    expect(screen.getByLabelText('密码')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '登录' })).toBeInTheDocument();
  });
});

describe('HistoryPage', () => {
  it('shows the empty state when there are no records', async () => {
    mockedApi.listDetections.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      pages: 0,
    });
    renderWithProviders(<HistoryPage />);
    expect(await screen.findByTestId('empty-panel')).toHaveTextContent('还没有检测记录');
  });

  it('shows an error panel when the request fails', async () => {
    mockedApi.listDetections.mockRejectedValue(new ApiError(500, 'INTERNAL_ERROR', '服务器内部错误'));
    renderWithProviders(<HistoryPage />);
    expect(await screen.findByTestId('error-panel')).toHaveTextContent('服务器内部错误');
  });

  it('renders history items and the record count', async () => {
    mockedApi.listDetections.mockResolvedValue({
      items: [
        {
          id: 1,
          prediction: 'benign',
          confidence: 0.91,
          probabilities: { benign: 0.91, malignant: 0.09 },
          model_version: '1.0.0+run_a',
          original_filename: 'a.jpg',
          image_available: false,
          created_at: '2026-01-01T00:00:00+00:00',
        },
        {
          id: 2,
          prediction: 'malignant',
          confidence: 0.77,
          probabilities: { benign: 0.23, malignant: 0.77 },
          model_version: '1.0.0+run_a',
          original_filename: 'b.jpg',
          image_available: false,
          created_at: '2026-01-02T00:00:00+00:00',
        },
      ],
      total: 2,
      page: 1,
      page_size: 10,
      pages: 1,
    });
    renderWithProviders(<HistoryPage />);
    await waitFor(() => expect(screen.getAllByTestId('history-item')).toHaveLength(2));
    expect(screen.getByTestId('history-total')).toHaveTextContent('共 2 条记录');
    expect(screen.getByText('良性倾向')).toBeInTheDocument();
    expect(screen.getByText('恶性倾向')).toBeInTheDocument();
  });
});
