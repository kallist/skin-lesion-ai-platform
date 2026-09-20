import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ResultCard from '../components/ResultCard';
import Disclaimer from '../components/Disclaimer';
import type { Detection } from '../types';

const baseDetection: Detection = {
  id: 7,
  prediction: 'malignant',
  confidence: 0.9321,
  probabilities: { benign: 0.0679, malignant: 0.9321 },
  model_version: '1.0.0+run_a_resnet50',
  original_filename: 'mole.jpg',
  image_available: true,
  disclaimer: 'AI辅助检测结果，仅供参考，不构成医学诊断。',
  advice: '模型检测结果倾向于恶性风险。该结果不能替代医生诊断，建议尽快由皮肤科专业人员进一步评估。',
  created_at: '2026-01-02T03:04:05+00:00',
};

describe('ResultCard', () => {
  it('renders malignant prediction with confidence and both probabilities', () => {
    render(<ResultCard detection={baseDetection} />);
    expect(screen.getByTestId('result-card')).toHaveAttribute('data-prediction', 'malignant');
    const heading = screen.getByRole('heading', { name: /检测结果/ });
    expect(heading).toBeInTheDocument();
    expect(screen.getByText('(Malignant)')).toBeInTheDocument();
    expect(screen.getByTestId('confidence')).toHaveTextContent('93.2%');
    // both class probability rows are rendered (labels are split across nodes)
    const bars = screen.getAllByRole('progressbar');
    expect(bars).toHaveLength(2);
    expect(screen.getByTestId('probability-bars').textContent).toContain('良性');
    expect(screen.getByTestId('probability-bars').textContent).toContain('恶性');
    expect(screen.getByTestId('model-version')).toHaveTextContent('1.0.0+run_a_resnet50');
  });

  it('renders benign prediction wording without alarming language', () => {
    render(
      <ResultCard
        detection={{
          ...baseDetection,
          prediction: 'benign',
          confidence: 0.88,
          probabilities: { benign: 0.88, malignant: 0.12 },
          advice: '模型检测结果倾向于良性，但 AI 检测不能完全排除风险。',
        }}
      />,
    );
    expect(screen.getByText('(Benign)')).toBeInTheDocument();
    expect(screen.getByTestId('confidence')).toHaveTextContent('88.0%');
  });

  it('always shows the medical disclaimer and calibration caveat', () => {
    render(<ResultCard detection={baseDetection} />);
    const disclaimer = screen.getByTestId('result-disclaimer');
    expect(disclaimer).toHaveTextContent('不构成医学诊断');
    expect(disclaimer).toHaveTextContent('模型置信度并不等同于真实临床患病概率');
  });

  it('never claims a diagnosis', () => {
    const { container } = render(<ResultCard detection={baseDetection} />);
    const text = container.textContent ?? '';
    for (const forbidden of ['你患有皮肤癌', '确诊', '100%', '无需就医', '保证']) {
      expect(text).not.toContain(forbidden);
    }
  });

  it('exposes probability bars with accessible values', () => {
    render(<ResultCard detection={baseDetection} />);
    const bars = screen.getAllByRole('progressbar');
    expect(bars).toHaveLength(2);
    expect(bars[1]).toHaveAttribute('aria-valuenow', '93');
  });
});

describe('Disclaimer', () => {
  it('renders the persistent full disclaimer', () => {
    render(<Disclaimer />);
    expect(screen.getByRole('note')).toHaveTextContent('本系统仅作为皮肤健康辅助自检工具');
    expect(screen.getByRole('note')).toHaveTextContent('不能替代专业医生诊断');
  });

  it('renders the compact variant', () => {
    render(<Disclaimer variant="compact" />);
    expect(screen.getByRole('note')).toHaveTextContent('AI辅助检测结果，仅供参考，不构成医学诊断。');
  });
});
