import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from supabase import create_client
import config

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

# ──────────────────────────────────────────────
# HOME — landing page
# ──────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ──────────────────────────────────────────────
# SUBMIT — customer data + image upload
# ──────────────────────────────────────────────
@app.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        nic = request.form.get("nic", "").strip()
        nationality = request.form.get("nationality", "").strip()
        alias = request.form.get("alias", "").strip()
        dob = request.form.get("dob", "").strip()
        email = request.form.get("email", "").strip()
        note = request.form.get("note", "").strip()
        image = request.files.get("image")

        # Validation
        if not full_name:
            flash("Full Name is required.", "danger")
            return render_template("submit.html")

        image_url = ""

        # Upload image to Supabase Storage if provided
        if image and image.filename:
            try:
                ext = image.filename.rsplit(".", 1)[-1].lower()
                filename = f"public/{uuid.uuid4().hex}.{ext}"
                file_bytes = image.read()
                content_type = image.content_type or "image/jpeg"

                supabase.storage.from_("uploads").upload(
                    path=filename,
                    file=file_bytes,
                    file_options={"content-type": content_type}
                )
                image_url = supabase.storage.from_("uploads").get_public_url(filename)
            except Exception as e:
                flash(f"Image upload failed: {e}", "danger")
                return render_template("submit.html")

        # Insert into submissions table
        try:
            data = {
                "full_name": full_name,
                "nic": nic if nic else None,
                "nationality": nationality if nationality else None,
                "alias": alias if alias else None,
                "dob": dob if dob else None,
                "email": email if email else None,
                "note": note if note else None,
                "image_url": image_url if image_url else None,
            }
            supabase.table("submissions").insert(data).execute()
            flash("Customer submitted successfully!", "success")
            return redirect(url_for("submit"))
        except Exception as e:
            flash(f"Database error: {e}", "danger")

    return render_template("submit.html")


# ──────────────────────────────────────────────
# REPORTS — screening results dashboard
# ──────────────────────────────────────────────
@app.route("/reports")
def reports():
    return render_template("reports.html")


# ──────────────────────────────────────────────
# API — fetch reports with search/filter
# ──────────────────────────────────────────────
@app.route("/api/reports")
def api_reports():
    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()

    try:
        query = supabase.table("screening_reports") \
            .select("*") \
            .order("risk_score", desc=True)

        if status:
            query = query.eq("status", status)

        if search:
            query = query.ilike("customer_name", f"%{search}%")

        result = query.execute()

        # Derive last_batch_time from the most recent screened_at
        last_batch_time = None
        if result.data:
            times = [r.get("screened_at") for r in result.data if r.get("screened_at")]
            if times:
                last_batch_time = max(times)

        return jsonify({
            "data": result.data,
            "count": len(result.data),
            "last_batch_time": last_batch_time
        })
    except Exception as e:
        return jsonify({"error": str(e), "data": [], "count": 0}), 500


# ──────────────────────────────────────────────
# API — single report detail by ID
# ──────────────────────────────────────────────
@app.route("/api/reports/<report_id>")
def api_report_detail(report_id):
    try:
        result = supabase.table("screening_reports") \
            .select("*") \
            .eq("id", report_id) \
            .execute()

        if not result.data:
            return jsonify({"error": "Not found"}), 404

        report = result.data[0]

        # Try to fetch the customer's image from submissions table
        image_url = None
        cust_name = report.get("customer_name", "")
        if cust_name:
            try:
                sub = supabase.table("submissions") \
                    .select("image_url") \
                    .ilike("full_name", cust_name) \
                    .limit(1) \
                    .execute()
                if sub.data and sub.data[0].get("image_url"):
                    image_url = sub.data[0]["image_url"]
            except:
                pass

        report["customer_image_url"] = image_url
        return jsonify({"data": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)