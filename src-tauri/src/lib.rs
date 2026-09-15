#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // Books run inside sandboxed iframes. This prototype exposes no native
    // commands or filesystem permissions to either the reader or book scripts.
    tauri::Builder::default()
        .setup(|app| {
            tauri::WebviewWindowBuilder::from_config(app, &app.config().app.windows[0])?
                .on_web_resource_request(|request, response| {
                    // Sandboxed books have an opaque Origin: null. Fonts and
                    // videos need the same resource CORS rule as the live server.
                    let path = request.uri().path();
                    if path.starts_with("/book/") || path.starts_with("/vendor/") {
                        response.headers_mut().insert(
                            tauri::http::header::ACCESS_CONTROL_ALLOW_ORIGIN,
                            tauri::http::HeaderValue::from_static("*"),
                        );
                    }
                })
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Grim");
}
