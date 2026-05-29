use stock_select_rs::cli::generate_completion_script;

#[test]
fn zsh_completion_includes_commands_and_recent_options() {
    let script = generate_completion_script("zsh").unwrap();

    assert!(script.contains("screen"));
    assert!(script.contains("analyze-symbol"));
    assert!(script.contains("--record"));
    assert!(script.contains("--no-progress"));
}
