/** 進捗（ウィザード）の各ステップを丸ノード+接続線で横並び表示するコンポーネント。 */
import type { ReactNode } from 'react'
import { cn } from './cn'

/** done=完了, active=現在, pending=未着手 */
export type StepState = 'done' | 'active' | 'pending'

export interface Step {
  key: string
  label: string
  /** ステップ右側に出す小さな補足（例: "3/12"）*/
  hint?: ReactNode
  state: StepState
  /** 指定すると、このステップのノードをクリック/Enterで遷移できるようにする */
  onClick?: () => void
}

interface StepperProps {
  steps: Step[]
  className?: string
}

// ステップの状態ごとの丸ノード・ラベル・接続線の配色クラス
const circleVariants: Record<StepState, string> = {
  done: 'bg-success-500 text-white border-success-500',
  active: 'bg-brand-600 text-white border-brand-600 ring-4 ring-brand-100',
  pending: 'bg-surface text-fg-subtle border-border-strong',
}

const labelVariants: Record<StepState, string> = {
  done: 'text-fg',
  active: 'text-brand-700 font-semibold',
  pending: 'text-fg-subtle',
}

const connectorVariants: Record<StepState, string> = {
  done: 'bg-success-500',
  active: 'bg-border-strong',
  pending: 'bg-border',
}

export function Stepper({ steps, className }: StepperProps) {
  return (
    <ol
      className={cn(
        'flex items-start gap-0 overflow-x-auto py-1',
        className,
      )}
      aria-label="進捗ステップ"
    >
      {steps.map((step, i) => {
        const isLast = i === steps.length - 1
        // onClick が指定されたステップだけ <button> にして操作可能にする（それ以外は非対話の <div>）
        const Wrapper = step.onClick ? 'button' : 'div'
        return (
          <li
            key={step.key}
            className="flex items-start gap-0 flex-1 min-w-[80px]"
            aria-current={step.state === 'active' ? 'step' : undefined}
          >
            <Wrapper
              type={step.onClick ? 'button' : undefined}
              onClick={step.onClick}
              className={cn(
                'flex flex-col items-center gap-1.5 shrink-0 w-full',
                step.onClick &&
                  'appearance-none bg-transparent border-0 p-0 m-0 font-inherit text-inherit cursor-pointer rounded-md hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 transition-opacity',
              )}
            >
              <div className="flex items-center w-full">
                <div className="flex-1 h-0.5" aria-hidden="true">
                  {i > 0 && (
                    <div
                      className={cn(
                        'h-full w-full',
                        connectorVariants[
                          steps[i - 1].state === 'done' ? 'done' : 'pending'
                        ],
                      )}
                    />
                  )}
                </div>
                <div
                  className={cn(
                    'flex items-center justify-center w-8 h-8 rounded-full border-2 text-sm font-semibold transition-all shrink-0',
                    circleVariants[step.state],
                  )}
                >
                  {step.state === 'done' ? (
                    <span aria-hidden="true">✓</span>
                  ) : (
                    i + 1
                  )}
                </div>
                <div className="flex-1 h-0.5" aria-hidden="true">
                  {!isLast && (
                    <div
                      className={cn(
                        'h-full w-full',
                        connectorVariants[
                          step.state === 'done' ? 'done' : 'pending'
                        ],
                      )}
                    />
                  )}
                </div>
              </div>
              <div className="flex flex-col items-center gap-0.5 px-1 text-center">
                <span
                  className={cn(
                    'text-xs leading-tight',
                    labelVariants[step.state],
                  )}
                >
                  {step.label}
                </span>
                {step.hint && (
                  <span className="text-[10px] text-fg-subtle leading-tight">
                    {step.hint}
                  </span>
                )}
              </div>
            </Wrapper>
          </li>
        )
      })}
    </ol>
  )
}
