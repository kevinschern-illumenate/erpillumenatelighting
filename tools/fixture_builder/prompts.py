"""Interactive prompt functions for the Fixture Builder CLI.

When YAML config fields are missing, these functions collect input
from the user interactively via stdin.
"""

from __future__ import annotations

from .config_schema import (
    FixtureBuilderConfig,
    ProfileDef,
    LensDef,
    AccessoryDef,
    EndcapDef,
    ProfileLensMapping,
    FixtureTemplateDef,
    TemplateAllowedOptions,
    DriverDef,
    SubmittalMappingDef,
    WebflowDef,
    TapeSpecDef,
    TapeOfferingDef,
    TapeNeonAllowedOptionDef,
    TapeNeonAllowedSpecDef,
    TapeNeonTemplateDef,
    NeonSubmittalMappingDef,
    TapeNeonWebflowDef,
)


def _input(prompt: str, default: str = "") -> str:
    """Prompt user with optional default."""
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()


def _input_int(prompt: str, default: int = 0) -> int:
    val = _input(prompt, str(default))
    return int(val) if val else default


def _input_float(prompt: str, default: float = 0.0) -> float:
    val = _input(prompt, str(default))
    return float(val) if val else default


def _input_bool(prompt: str, default: bool = True) -> bool:
    val = _input(prompt, "y" if default else "n")
    return val.lower() in ("y", "yes", "1", "true")


def _input_list(prompt: str, default: str = "") -> list[str]:
    """Prompt for a comma-separated list."""
    val = _input(f"{prompt} (comma-separated)", default)
    return [x.strip() for x in val.split(",") if x.strip()]


def prompt_series_info(config: FixtureBuilderConfig) -> None:
    """Prompt for series-level info if not in config."""
    if not config.series_name:
        config.series_name = _input("Series name (e.g., Castle)")
    if not config.series_code:
        config.series_code = _input("Series code prefix (e.g., CA)", config.series_name[:2].upper())


def prompt_profiles(config: FixtureBuilderConfig) -> None:
    """Prompt for profile definitions if empty."""
    if config.profiles:
        return

    print("\n── Profile Family Definitions ──")
    while True:
        family = _input("Profile family code (e.g., CA01, or blank to finish)")
        if not family:
            break

        label = _input("Variant label (e.g., [WD], [RC])", "")
        finishes = _input_list("Finishes", "WH,BK,SV")
        width = _input_float("Width (mm)")
        height = _input_float("Height (mm)")
        stock_len = _input_int("Stock length (mm)", 2000)
        max_len = _input_int("Max assembled length (mm)", 2500)
        cuttable = _input_bool("Is cuttable?", True)
        joiners = _input_bool("Supports joiners?", False)
        joiner_sys = ""
        if joiners:
            joiner_sys = _input("Joiner system", "")
        lens_iface = _input("Lens interface", "Snap-in")
        env_ratings = _input_list("Environment ratings", "Dry")

        config.profiles.append(ProfileDef(
            family=family, variant_label=label, finishes=finishes,
            width_mm=width, height_mm=height,
            stock_length_mm=stock_len, max_assembled_length_mm=max_len,
            is_cuttable=cuttable, supports_joiners=joiners,
            joiner_system=joiner_sys, lens_interface=lens_iface,
            environment_ratings=env_ratings,
        ))
        print(f"  Added profile {family}")


def prompt_lenses(config: FixtureBuilderConfig) -> None:
    """Prompt for lens definitions if empty."""
    if config.lenses:
        return

    print("\n── Lens Family Definitions ──")
    while True:
        family = _input("Lens family code (e.g., CAXX, CH01, or blank to finish)")
        if not family:
            break

        appearances = _input_list("Lens appearances", "White")
        shape = _input("Shape code for item code (e.g., WH, RD)", "WH")
        stock_type = _input("Stock type (Stick/Continuous Roll)", "Stick")
        stock_len = _input_int("Stock length (mm)", 2000)

        config.lenses.append(LensDef(
            family=family, appearances=appearances, shape=shape,
            stock_type=stock_type, stock_length_mm=stock_len,
        ))
        print(f"  Added lens family {family}")


def prompt_profile_lens_mappings(config: FixtureBuilderConfig) -> None:
    """Prompt for profile → lens mappings if empty."""
    if config.profile_lens_mappings:
        return

    print("\n── Profile → Lens Mappings ──")
    families = [p.family for p in config.profiles]
    lens_families = [l.family for l in config.lenses]
    print(f"  Available profiles: {', '.join(families)}")
    print(f"  Available lens families: {', '.join(lens_families)}")

    while True:
        pf = _input("Profile families (comma-separated, or blank to finish)")
        if not pf:
            break
        profile_fams = [x.strip() for x in pf.split(",")]
        lens_fam = _input("Maps to lens family")

        config.profile_lens_mappings.append(ProfileLensMapping(
            profile_families=profile_fams, lens_family=lens_fam,
        ))


def prompt_accessories(config: FixtureBuilderConfig) -> None:
    """Prompt for accessory definitions if empty."""
    if config.accessories:
        return

    print("\n── Accessory Definitions ──")
    print("  Types: Mounting, Joiner")

    while True:
        item_code = _input("Accessory item code (e.g., ACC-CAXX-MC, or blank to finish)")
        if not item_code:
            break

        acc_type = _input("Type (Mounting/Joiner)", "Mounting")
        pfamily = _input("Profile family", "")
        mounting = ""
        joiner_sys = ""
        joiner_angle = ""
        qty_rule_type = "Per x mm"
        qty_rule_value = 304.8

        if acc_type == "Mounting":
            mounting = _input("Mounting method", "Mounting Clip")
            qty_rule_type = _input("QTY rule type", "Per x mm")
            qty_rule_value = _input_float("QTY rule value (mm)", 304.8)
        elif acc_type == "Joiner":
            joiner_sys = _input("Joiner system (blank for generic)", "")
            joiner_angle = _input("Joiner angle (blank for generic)", "")
            qty_rule_type = "Per Joint"
            qty_rule_value = 1

        config.accessories.append(AccessoryDef(
            item_code=item_code, accessory_type=acc_type,
            profile_family=pfamily, mounting_method=mounting,
            joiner_system=joiner_sys, joiner_angle=joiner_angle,
            qty_rule_type=qty_rule_type, qty_rule_value=qty_rule_value,
        ))
        print(f"  Added accessory {item_code}")


def prompt_endcaps(config: FixtureBuilderConfig) -> None:
    """Prompt for endcap definitions per profile family if empty."""
    if config.endcaps:
        return

    print("\n── Endcap Definitions ──")
    for profile in config.profiles:
        add = _input_bool(f"Add endcaps for {profile.family}?", True)
        if add:
            colors = _input_list("Endcap colors (codes)", "WH,BK,GR")
            styles = _input_list("Endcap styles", "Solid,Feed Through")
            allowance = _input_float("Allowance override per side (mm)", 2.0)

            config.endcaps.append(EndcapDef(
                profile_family=profile.family,
                colors=colors, styles=styles,
                allowance_override_per_side_mm=allowance,
            ))


def prompt_fixture_templates(config: FixtureBuilderConfig) -> None:
    """Prompt for fixture template settings — per profile × LED package.

    First asks for global LED packages and assembly defaults,
    then loops per profile family × LED package asking for allowed options.
    If template_overrides are already populated, skip.
    """
    ft = config.fixture_templates

    # Ask for LED packages (global across all templates)
    if ft.led_packages == ["FS", "SW", "TW"]:
        print("\n── Fixture Template Settings ──")
        ft.led_packages = _input_list("LED packages", ",".join(ft.led_packages))

    # If overrides already populated (from YAML), skip interactive loop
    if config.template_overrides:
        return

    # If global allowed options are already populated (from YAML without overrides),
    # use them as defaults and skip interactive loop
    if ft.allowed_finishes and ft.allowed_lenses:
        return

    # Ask per profile × LED package
    print("\n── Per-Template Allowed Options ──")
    print("  For each profile × LED package, specify allowed options.")
    print('  Press Enter to accept defaults, or type "same" to reuse the previous answers.\n')

    prev_opts = None
    for profile in config.profiles:
        for led_pkg in ft.led_packages:
            template_code = f"ILL-{profile.family}-{led_pkg}"
            print(f"\n  ── {template_code} ({profile.variant_label or profile.family}, {led_pkg}) ──")

            if prev_opts is not None:
                reuse = _input("  Reuse previous answers? (y/n)", "y")
                if reuse.lower() in ("y", "yes"):
                    config.template_overrides.append(TemplateAllowedOptions(
                        profile_family=profile.family,
                        led_package=led_pkg,
                        allowed_finishes=list(prev_opts.allowed_finishes),
                        allowed_lenses=list(prev_opts.allowed_lenses),
                        allowed_mountings=list(prev_opts.allowed_mountings),
                        allowed_endcap_styles=list(prev_opts.allowed_endcap_styles),
                        allowed_power_feed_types=list(prev_opts.allowed_power_feed_types),
                        allowed_environment_ratings=list(prev_opts.allowed_environment_ratings),
                        tape_offerings=list(prev_opts.tape_offerings),
                        base_price_msrp=prev_opts.base_price_msrp,
                        price_per_ft_msrp=prev_opts.price_per_ft_msrp,
                    ))
                    print(f"    ✓ Copied from previous")
                    continue

            finishes = _input_list("Allowed finishes (names)", "White,Black,Anodized Silver")
            lenses = _input_list("Allowed lens appearances", "White")
            mountings = _input_list("Allowed mounting methods", "Mounting Clip")
            endcap_styles = _input_list("Allowed endcap styles", "Solid,Feed Through")
            power_feeds = _input_list("Allowed power feed types", "")
            env_ratings = _input_list("Allowed environment ratings", "Dry")
            tape_offs = _input_list("Tape offerings (item codes)", "")
            base_price = _input_float("Base price MSRP", 0.0)
            per_ft_price = _input_float("Price per ft MSRP", 0.0)

            opts = TemplateAllowedOptions(
                profile_family=profile.family,
                led_package=led_pkg,
                allowed_finishes=finishes,
                allowed_lenses=lenses,
                allowed_mountings=mountings,
                allowed_endcap_styles=endcap_styles,
                allowed_power_feed_types=power_feeds,
                allowed_environment_ratings=env_ratings,
                tape_offerings=tape_offs,
                base_price_msrp=base_price,
                price_per_ft_msrp=per_ft_price,
            )
            config.template_overrides.append(opts)
            prev_opts = opts
            print(f"    ✓ Added")


def prompt_drivers(config: FixtureBuilderConfig) -> None:
    """Prompt for driver eligibility if defaults."""
    if config.drivers.driver_specs == ["PS-UNIV-24V-100W-IP66"]:
        specs = _input_list("Driver specs", "PS-UNIV-24V-100W-IP66")
        config.drivers.driver_specs = specs


def prompt_submittal_mapping(config: FixtureBuilderConfig) -> None:
    """Prompt for submittal mapping config."""
    if not config.submittal_mapping.clone_from_template:
        config.submittal_mapping.clone_from_template = _input(
            "Clone submittal mappings from template (e.g., ILL-AX01-FS)", "ILL-AX01-FS"
        )


def prompt_all(config: FixtureBuilderConfig) -> None:
    """Run all interactive prompts for missing config."""
    prompt_series_info(config)

    if config.product_type in ("tape", "neon"):
        prompt_all_tape_neon(config)
        return

    if config.mode == "new-family":
        prompt_profiles(config)
        prompt_lenses(config)
        prompt_profile_lens_mappings(config)
        prompt_accessories(config)
        prompt_endcaps(config)

    prompt_fixture_templates(config)
    prompt_drivers(config)
    prompt_submittal_mapping(config)


# ── Tape / Neon prompts ───────────────────────────────────────────────

def prompt_all_tape_neon(config: FixtureBuilderConfig) -> None:
    """Run all interactive prompts for tape/neon config."""
    is_neon = config.product_type == "neon"
    category = "LED Neon" if is_neon else "LED Tape"

    if config.mode == "new-family":
        prompt_tape_specs(config, category)
        prompt_tape_offerings(config)

    prompt_tape_neon_templates(config, category, is_neon)
    prompt_neon_submittal_mapping(config)
    prompt_tape_neon_webflow(config, is_neon)


def prompt_tape_specs(config: FixtureBuilderConfig, category: str) -> None:
    """Prompt for tape spec definitions if empty."""
    if config.tape_specs:
        return

    print(f"\n── {category} Spec Definitions ──")
    while True:
        item_code = _input("Tape spec item code (e.g., TAPE-FS-24V-4.4W, or blank to finish)")
        if not item_code:
            break

        led_pkg = _input("LED package (e.g., FS, SW, TW)", "FS")
        voltage = _input("Input voltage", "24V DC")
        wpf = _input_float("Watts per foot", 0.0)
        lpf = _input_float("Lumens per foot", 0.0)
        cri = _input_int("CRI typical", 90)
        pitch = _input_float("LED pitch (mm)", 0.0)
        pcb_mount = _input("PCB mounting (e.g., Adhesive Backed)", "")
        pcb_fin = _input("PCB finish (e.g., White)", "")
        cut_inc = _input_float("Cut increment (mm)", 0.0)
        free_cut = _input_bool("Is free cutting?", False)
        leader = _input("Leader cable item", "")
        dimming = _input_list("Dimming protocols", "")

        config.tape_specs.append(TapeSpecDef(
            item_code=item_code,
            led_package=led_pkg,
            product_category=category,
            input_voltage=voltage,
            watts_per_foot=wpf,
            lumens_per_foot=lpf,
            cri_typical=cri,
            led_pitch_mm=pitch,
            pcb_mounting=pcb_mount,
            pcb_finish=pcb_fin,
            cut_increment_mm=cut_inc,
            is_free_cutting=free_cut,
            leader_cable_item=leader,
            dimming_protocols=dimming,
        ))
        print(f"  Added tape spec {item_code}")


def prompt_tape_offerings(config: FixtureBuilderConfig) -> None:
    """Prompt for tape offerings if empty."""
    if config.tape_offerings:
        return

    print("\n── Tape Offering Definitions ──")
    print("  Define CCT × Output Level combinations per tape spec.")

    for ts in config.tape_specs:
        print(f"\n  ── Offerings for {ts.item_code} ──")
        while True:
            cct = _input(f"  CCT (e.g., 2700K, or blank to finish {ts.item_code})")
            if not cct:
                break
            output_level = _input("  Output level", "Standard")
            cri = _input_int("  CRI", ts.cri_typical)
            sdcm = _input_int("  SDCM", 3)
            wpf_override = _input_float("  Watts/ft override (0 = use spec default)", 0.0)
            cut_override = _input_float("  Cut increment override (0 = use spec default)", 0.0)

            config.tape_offerings.append(TapeOfferingDef(
                tape_spec=ts.item_code,
                cct=cct,
                cri=cri,
                sdcm=sdcm,
                led_package=ts.led_package,
                output_level=output_level,
                watts_per_ft_override=wpf_override,
                cut_increment_mm_override=cut_override,
            ))
            print(f"    Added offering: {ts.item_code} / {cct} / {output_level}")


def prompt_tape_neon_templates(config: FixtureBuilderConfig, category: str,
                               is_neon: bool) -> None:
    """Prompt for tape/neon template definitions if empty."""
    if config.tape_neon_templates:
        return

    print(f"\n── {category} Template Definitions ──")
    while True:
        code = _input("Template code (e.g., ILL-TNF-FS, or blank to finish)")
        if not code:
            break

        name = _input("Template name", f"{config.series_name} {category}")
        default_spec = ""
        if config.tape_specs:
            default_spec = _input("Default tape spec", config.tape_specs[0].item_code)
        base_price = _input_float("Base price MSRP", 0.0)
        per_ft = _input_float("Price per ft MSRP", 0.0)
        pricing_basis = _input("Pricing length basis", "L_tape_cut")
        leader = _input_int("Leader allowance (mm)", 15)

        # Allowed tape specs
        allowed_specs = []
        if config.tape_specs:
            print("  Select allowed tape specs for this template:")
            for i, ts in enumerate(config.tape_specs):
                use = _input_bool(f"    Allow {ts.item_code}?", True)
                if use:
                    is_def = (ts.item_code == default_spec)
                    env_rating = _input(f"    Environment rating for {ts.item_code}", "")
                    allowed_specs.append(TapeNeonAllowedSpecDef(
                        tape_spec=ts.item_code,
                        is_default=is_def,
                        environment_rating=env_rating,
                    ))

        # Allowed options
        allowed_options = []

        # CCT options
        ccts = _input_list("Allowed CCTs", "")
        for i, cct in enumerate(ccts):
            adder = _input_float(f"  MSRP adder for CCT={cct}", 0.0)
            allowed_options.append(TapeNeonAllowedOptionDef(
                option_type="CCT", value=cct,
                is_default=(i == 0), msrp_adder=adder,
            ))

        # Output Level options
        outputs = _input_list("Allowed output levels", "Standard")
        for i, ol in enumerate(outputs):
            adder = _input_float(f"  MSRP adder for Output Level={ol}", 0.0)
            allowed_options.append(TapeNeonAllowedOptionDef(
                option_type="Output Level", value=ol,
                is_default=(i == 0), msrp_adder=adder,
            ))

        # Environment Rating options
        env_ratings = _input_list("Allowed environment ratings", "Dry")
        for i, er in enumerate(env_ratings):
            adder = _input_float(f"  MSRP adder for Environment={er}", 0.0)
            allowed_options.append(TapeNeonAllowedOptionDef(
                option_type="Environment Rating", value=er,
                is_default=(i == 0), msrp_adder=adder,
            ))

        # Feed Direction options
        feed_dirs = _input_list("Allowed feed directions", "Single Feed")
        for i, fd in enumerate(feed_dirs):
            adder = _input_float(f"  MSRP adder for Feed Direction={fd}", 0.0)
            allowed_options.append(TapeNeonAllowedOptionDef(
                option_type="Feed Direction", value=fd,
                is_default=(i == 0), msrp_adder=adder,
            ))

        # Neon-specific options
        if is_neon:
            # IP Rating
            ip_ratings = _input_list("Allowed IP ratings", "IP67")
            for i, ip in enumerate(ip_ratings):
                adder = _input_float(f"  MSRP adder for IP={ip}", 0.0)
                allowed_options.append(TapeNeonAllowedOptionDef(
                    option_type="IP Rating", value=ip,
                    is_default=(i == 0), msrp_adder=adder,
                ))

            # Mounting Method
            mountings = _input_list("Allowed mounting methods", "")
            for i, m in enumerate(mountings):
                adder = _input_float(f"  MSRP adder for Mounting={m}", 0.0)
                allowed_options.append(TapeNeonAllowedOptionDef(
                    option_type="Mounting Method", value=m,
                    is_default=(i == 0), msrp_adder=adder,
                ))

            # Finish
            finishes = _input_list("Allowed finishes", "")
            for i, f in enumerate(finishes):
                adder = _input_float(f"  MSRP adder for Finish={f}", 0.0)
                allowed_options.append(TapeNeonAllowedOptionDef(
                    option_type="Finish", value=f,
                    is_default=(i == 0), msrp_adder=adder,
                ))

            # Endcap Style
            endcap_styles = _input_list("Allowed endcap styles", "")
            for i, es in enumerate(endcap_styles):
                adder = _input_float(f"  MSRP adder for Endcap Style={es}", 0.0)
                allowed_options.append(TapeNeonAllowedOptionDef(
                    option_type="Endcap Style", value=es,
                    is_default=(i == 0), msrp_adder=adder,
                ))

        config.tape_neon_templates.append(TapeNeonTemplateDef(
            template_code=code,
            template_name=name,
            product_category=category,
            series=config.series_name,
            default_tape_spec=default_spec,
            base_price_msrp=base_price,
            price_per_ft_msrp=per_ft,
            pricing_length_basis=pricing_basis,
            leader_allowance_mm=leader,
            allowed_tape_specs=allowed_specs,
            allowed_options=allowed_options,
        ))
        print(f"  Added template {code}")


def prompt_neon_submittal_mapping(config: FixtureBuilderConfig) -> None:
    """Prompt for neon submittal mapping config."""
    if not config.neon_submittal_mapping.clone_from_template:
        config.neon_submittal_mapping.clone_from_template = _input(
            "Clone neon submittal mappings from template (blank for defaults)", ""
        )


def prompt_tape_neon_webflow(config: FixtureBuilderConfig, is_neon: bool) -> None:
    """Prompt for tape/neon webflow config if defaults."""
    wf = config.tape_neon_webflow
    if wf.product_category in ("led-tape", "led-neon") and wf.configurator_steps:
        return  # Already configured from YAML

    default_cat = "led-neon" if is_neon else "led-tape"
    wf.product_category = _input("Webflow product category", default_cat)
    steps = _input_list("Configurator step order",
                        ",".join(wf.configurator_steps))
    if steps:
        wf.configurator_steps = steps
