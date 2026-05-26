fn main() {
    if let Err(err) = stock_select_rs::cli::run() {
        eprintln!("error: {err:#}");
        std::process::exit(1);
    }
}
