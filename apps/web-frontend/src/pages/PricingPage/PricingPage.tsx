import React, { useState } from 'react';
import { Link } from 'react-router-dom';

interface Feature {
  text: string;
}

interface PricingCardProps {
  name: string;
  price: string;
  period?: string;
  tagline: string;
  features: Feature[];
  ctaLabel: string;
  ctaHref: string;
  ctaExternal?: boolean;
  highlighted?: boolean;
  badge?: string;
}

const CheckIcon: React.FC = () => (
  <svg
    className="h-4 w-4 flex-shrink-0 text-emerald-400"
    viewBox="0 0 20 20"
    fill="currentColor"
    aria-hidden="true"
  >
    <path
      fillRule="evenodd"
      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
      clipRule="evenodd"
    />
  </svg>
);

const PricingCard: React.FC<PricingCardProps> = ({
  name,
  price,
  period,
  tagline,
  features,
  ctaLabel,
  ctaHref,
  ctaExternal = false,
  highlighted = false,
  badge,
}) => {
  const cardBase =
    'relative flex flex-col rounded-2xl border p-8 transition-shadow duration-200';
  const cardStyle = highlighted
    ? `${cardBase} border-emerald-400/60 bg-slate-900 shadow-[0_0_40px_0_rgba(52,211,153,0.12)]`
    : `${cardBase} border-slate-800 bg-slate-900/60`;

  const ctaBase =
    'mt-8 block w-full rounded-lg px-4 py-3 text-center text-sm font-semibold transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2 focus:ring-offset-slate-950';
  const ctaStyle = highlighted
    ? `${ctaBase} bg-emerald-400 text-slate-950 hover:bg-emerald-300`
    : `${ctaBase} border border-slate-700 bg-transparent text-slate-100 hover:border-emerald-400/60 hover:text-emerald-400`;

  const cta = ctaExternal ? (
    <a href={ctaHref} className={ctaStyle}>
      {ctaLabel}
    </a>
  ) : (
    <Link to={ctaHref} className={ctaStyle}>
      {ctaLabel}
    </Link>
  );

  return (
    <div className={cardStyle}>
      {badge && (
        <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-emerald-400 px-3 py-0.5 text-xs font-bold uppercase tracking-wide text-slate-950">
          {badge}
        </span>
      )}

      <div>
        <h2 className="text-lg font-semibold text-slate-100">{name}</h2>
        <p className="mt-1 text-sm text-slate-400">{tagline}</p>
        <div className="mt-6 flex items-end gap-1">
          <span className="text-4xl font-extrabold text-slate-100">{price}</span>
          {period && <span className="mb-1 text-sm text-slate-400">{period}</span>}
        </div>
      </div>

      <ul className="mt-8 space-y-3 flex-1">
        {features.map((f, i) => (
          <li key={i} className="flex items-center gap-3 text-sm text-slate-300">
            <CheckIcon />
            <span>{f.text}</span>
          </li>
        ))}
      </ul>

      {cta}
    </div>
  );
};

interface FaqItem {
  question: string;
  answer: string;
}

const FaqAccordion: React.FC<{ items: FaqItem[] }> = ({ items }) => {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <div className="divide-y divide-slate-800 rounded-xl border border-slate-800">
      {items.map((item, i) => (
        <div key={i}>
          <button
            className="flex w-full items-center justify-between px-6 py-5 text-left"
            onClick={() => setOpenIndex(openIndex === i ? null : i)}
            aria-expanded={openIndex === i}
          >
            <span className="text-sm font-medium text-slate-100">{item.question}</span>
            <svg
              className={`h-5 w-5 flex-shrink-0 text-slate-400 transition-transform duration-200 ${openIndex === i ? 'rotate-180' : ''}`}
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
          </button>
          {openIndex === i && (
            <div className="px-6 pb-5">
              <p className="text-sm text-slate-400">{item.answer}</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

const FREE_FEATURES: Feature[] = [
  { text: '5 active workflows' },
  { text: '100 executions/month' },
  { text: 'All node types' },
  { text: 'Community support' },
  { text: '1 GB memory storage' },
];

const PRO_FEATURES: Feature[] = [
  { text: 'Unlimited workflows' },
  { text: 'Unlimited executions' },
  { text: 'Priority support' },
  { text: 'Advanced analytics' },
  { text: 'Workflow versioning' },
  { text: 'Team collaboration (5 seats)' },
];

const ENTERPRISE_FEATURES: Feature[] = [
  { text: 'Everything in Pro' },
  { text: 'SSO + SAML' },
  { text: 'On-premise deployment' },
  { text: 'SLA guarantee' },
  { text: 'Dedicated support' },
  { text: 'Custom integrations' },
];

const FAQ_ITEMS: FaqItem[] = [
  {
    question: 'Can I self-host?',
    answer:
      'Yes — SynApps ships with a Docker Compose setup that gets you running with a single command. See the deploy guide for full instructions.',
  },
  {
    question: 'What counts as an execution?',
    answer:
      'Each time a workflow runs end-to-end counts as 1 execution. A partial run that errors out mid-way still counts as 1 execution.',
  },
  {
    question: 'Is my data private?',
    answer:
      'Yes — your workflows and data stay in your account and are never used for training. If you self-host, everything runs on your own infrastructure.',
  },
  {
    question: 'Can I upgrade or downgrade?',
    answer:
      'Yes, you can change your plan at any time from your account settings. Upgrades take effect immediately; downgrades apply at the end of the billing cycle.',
  },
];

const PricingPage: React.FC = () => {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Header */}
      <div className="mx-auto max-w-7xl px-4 pt-20 pb-4 text-center sm:px-6 lg:px-8">
        <h1 className="text-4xl font-extrabold tracking-tight text-slate-100 sm:text-5xl">
          Simple, transparent pricing
        </h1>
        <p className="mt-4 text-lg text-slate-400">Start free. Scale when you&apos;re ready.</p>
      </div>

      {/* Pricing cards */}
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="grid gap-8 md:grid-cols-3">
          <PricingCard
            name="Free"
            price="$0"
            period="/mo"
            tagline="For individuals &amp; experimentation"
            features={FREE_FEATURES}
            ctaLabel="Get Started Free"
            ctaHref="/register"
          />
          <PricingCard
            name="Pro"
            price="$29"
            period="/mo"
            tagline="For teams &amp; production"
            features={PRO_FEATURES}
            ctaLabel="Start Pro Trial"
            ctaHref="/register?plan=pro"
            highlighted
            badge="Most Popular"
          />
          <PricingCard
            name="Enterprise"
            price="Custom"
            tagline="For organizations at scale"
            features={ENTERPRISE_FEATURES}
            ctaLabel="Contact Sales"
            ctaHref="mailto:sales@nxtg.ai"
            ctaExternal
          />
        </div>
      </div>

      {/* FAQ */}
      <div className="mx-auto max-w-3xl px-4 pb-24 sm:px-6 lg:px-8">
        <h2 className="mb-8 text-center text-2xl font-bold text-slate-100">
          Frequently asked questions
        </h2>
        <FaqAccordion items={FAQ_ITEMS} />
      </div>
    </div>
  );
};

export default PricingPage;
