/** Persistent medical disclaimer — shown on every page that could be mistaken
 *  for a diagnosis.  Not dismissible by design. */
export default function Disclaimer({ variant = 'full' }: { variant?: 'full' | 'compact' }) {
  if (variant === 'compact') {
    return (
      <p
        role="note"
        className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
      >
        AI辅助检测结果，仅供参考，不构成医学诊断。
      </p>
    );
  }
  return (
    <aside
      role="note"
      aria-label="医疗免责声明"
      className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
    >
      <p className="font-semibold">⚠ 医疗免责声明</p>
      <p className="mt-1.5 leading-relaxed">
        本系统仅作为皮肤健康辅助自检工具，检测结果仅供参考，
        <strong>不能替代专业医生诊断</strong>。模型置信度并不等同于真实临床患病概率。
        如皮损出现快速增大、颜色改变、破溃、出血或你仍有疑虑，请及时就医并咨询皮肤科医生。
      </p>
    </aside>
  );
}
