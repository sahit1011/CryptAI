import { Navbar } from "@/components/landing/Navbar";
import { LandingDock } from "@/components/landing/LandingDock";
import { SmoothScroll } from "@/components/landing/SmoothScroll";
import { HeroSection } from "@/components/landing/HeroSection";
import { FeaturesSection } from "@/components/landing/FeaturesSection";
import { StatsSection } from "@/components/landing/StatsSection";
import { ArchitectureSection } from "@/components/landing/ArchitectureSection";
import { ProofSection } from "@/components/landing/ProofSection";
import { PricingSection } from "@/components/landing/PricingSection";
import { FaqSection } from "@/components/landing/FaqSection";
import { CTASection } from "@/components/landing/CTASection";
import { Footer } from "@/components/landing/Footer";

/*
 * Landing composition — one continuous crimson atmosphere on bg-background.
 * Order: Hero (with its own aurora) → Features → Stats → Architecture → CTA.
 * Selection is crimson to match the brand. No hardcoded canvas hex.
 */
export default function LandingPage() {
    return (
        <div className="grain min-h-screen bg-background text-foreground overflow-x-hidden font-sans selection:bg-accent/30 selection:text-foreground">
            <SmoothScroll>
            <Navbar />
            <LandingDock />

            <main>
                <HeroSection />
                <FeaturesSection />
                <StatsSection />
                <ArchitectureSection />
                <ProofSection />
                <PricingSection />
                <FaqSection />
                <CTASection />
            </main>

            <Footer />
            </SmoothScroll>
        </div>
    );
}
