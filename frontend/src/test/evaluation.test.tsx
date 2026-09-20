import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import EvaluationPage from '../pages/EvaluationPage';
import { EXTERNAL_TEST, INTERNAL_TEST, pointDelta } from '../data/evaluation';

function renderPage() {
  return render(
    <MemoryRouter>
      <EvaluationPage />
    </MemoryRouter>,
  );
}

describe('EvaluationPage', () => {
  it('shows both the internal and the independent external results', () => {
    renderPage();
    // 92.96% (internal) and 78.54% (external) are the real artifact values.
    expect(screen.getAllByText('92.96%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('78.54%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('内部测试集').length).toBeGreaterThan(0);
    expect(screen.getAllByText('独立外部测试集').length).toBeGreaterThan(0);
  });

  it('states that the external accuracy target was not met', () => {
    const { container } = renderPage();
    expect(container.textContent).toContain('独立外部测试集未达标');
  });

  it('reports the malignant recall drop and the false negatives', () => {
    const { container } = renderPage();
    const recallDrop = pointDelta(INTERNAL_TEST.recall, EXTERNAL_TEST.recall).toFixed(2);
    expect(container.textContent).toContain(`${recallDrop} pt`);
    expect(container.textContent).toContain('65.49%');
    expect(container.textContent).toContain(`${EXTERNAL_TEST.confusion.fn} 例恶性样本被判为良性`);
  });

  it('keeps the leakage-check numbers and the "no retraining" statement visible', () => {
    const { container } = renderPage();
    expect(container.textContent).toContain('train 0 / val 0 / test 0');
    expect(container.textContent).toContain('未针对测试集重新训练或调整最终阈值');
    expect(container.textContent).toContain('NOT IMPLEMENTED');
  });

  it('renders the real evaluation plots and always carries the medical disclaimer', () => {
    const { container } = renderPage();
    expect(screen.getByAltText('独立外部测试集 ROC 曲线')).toBeInTheDocument();
    expect(screen.getByAltText('独立外部测试集 PR 曲线')).toBeInTheDocument();
    expect(screen.getByAltText('内部测试集混淆矩阵图')).toBeInTheDocument();
    expect(container.textContent).toContain('不能替代专业医生诊断');
    expect(container.textContent).toContain('不代表新增的模型能力');
  });
});
