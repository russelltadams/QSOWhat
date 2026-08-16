import os
import json
import datetime
from flask import render_template, request, redirect, url_for, flash, session, send_file, abort
from werkzeug.utils import secure_filename
from app import app, admin_required, ADMIN_USERNAME, ADMIN_PASSWORD
from adif_parser import parse_adif_file
from qsl_generator import generate_qsl_card
from models import load_station_log, save_station_log, load_blog_posts, save_blog_posts, merge_contacts
from config_manager import load_config, save_config, get_config_value
import logging

@app.route('/')
def index():
    """Home page showing recent contacts and station statistics"""
    station_log = load_station_log()
    blog_posts = load_blog_posts()
    config = load_config()
    
    # Get recent contacts limit from config
    recent_limit = config.get('display', {}).get('recent_contacts_limit', 10)
    
    # Sort all contacts by date/time and get the most recent ones
    if station_log['contacts']:
        sorted_contacts = sorted(station_log['contacts'], 
                               key=lambda x: (x.get('qso_date', ''), x.get('time_on', '')), 
                               reverse=True)
        recent_contacts = sorted_contacts[:recent_limit]
    else:
        recent_contacts = []
    
    # Calculate statistics
    total_contacts = len(station_log['contacts'])
    confirmed_contacts = sum(1 for contact in station_log['contacts']
                              if contact.get('qsl_rcvd', '').upper() in ['Y', 'YES'])
    unique_bands = set(contact.get('band', '').upper() for contact in station_log['contacts'] if contact.get('band'))
    unique_modes = set(contact.get('mode', '').upper() for contact in station_log['contacts'] if contact.get('mode'))
    unique_countries = set(contact.get('country', '') for contact in station_log['contacts'] if contact.get('country'))
    
    # Get latest blog posts (last 4)
    latest_posts = blog_posts['posts'][-4:] if blog_posts['posts'] else []
    latest_posts.reverse()  # Show newest first
    
    stats = {
        'total_contacts': total_contacts,
        'confirmed_contacts': confirmed_contacts,
        'total_bands': len(unique_bands),
        'total_modes': len(unique_modes),
        'total_countries': len(unique_countries)
    }
    
    return render_template('index.html', 
                         recent_contacts=recent_contacts,
                         stats=stats,
                         latest_posts=latest_posts,
                         station_callsign=station_log['header'].get('station_callsign', 'KM6KFX'))

@app.route('/blog')
def blog():
    """Blog page showing all posts"""
    blog_posts = load_blog_posts()
    posts = blog_posts['posts'][::-1]  # Show newest first
    return render_template('blog.html', posts=posts)

@app.route('/blog/<int:post_id>')
def blog_post(post_id):
    """Individual blog post page"""
    blog_posts = load_blog_posts()
    post = next((p for p in blog_posts['posts'] if p['id'] == post_id), None)
    if not post:
        abort(404)
    return render_template('blog_post.html', post=post)

@app.route('/view_log')
def view_log():
    """View all contacts with pagination"""
    station_log = load_station_log()
    config = load_config()
    
    page = request.args.get('page', 1, type=int)
    per_page = config.get('display', {}).get('contacts_per_page', 50)
    
    # Sort contacts by date/time in descending order (newest first)
    sorted_contacts = sorted(station_log['contacts'], 
                           key=lambda x: (x.get('qso_date', ''), x.get('time_on', '')), 
                           reverse=True)
    
    total_contacts = len(sorted_contacts)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    contacts = sorted_contacts[start_idx:end_idx]
    
    # Calculate pagination info
    total_pages = (total_contacts + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    return render_template('view_log.html',
                         contacts=contacts,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         total_contacts=total_contacts)

@app.route('/contact/<int:contact_index>')
def contact_details(contact_index):
    """View individual contact details"""
    station_log = load_station_log()
    
    if contact_index < 0 or contact_index >= len(station_log['contacts']):
        abort(404)
    
    contact = station_log['contacts'][contact_index]
    return render_template('contact_details.html', contact=contact, contact_index=contact_index)

@app.route('/search')
def search():
    """Search contacts"""
    station_log = load_station_log()
    
    # Get search parameters
    query = request.args.get('q', '').strip()
    call_filter = request.args.get('call', '').strip()
    grid_filter = request.args.get('grid', '').strip()
    band_filter = request.args.get('band', '').strip()
    mode_filter = request.args.get('mode', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    page = request.args.get('page', 1, type=int)
    
    all_contacts = station_log['contacts']
    
    # Create a list of (contact, original_index) tuples to track original indices
    indexed_contacts = [(contact, idx) for idx, contact in enumerate(all_contacts)]
    
    # Apply filters
    if query:
        query_lower = query.lower()
        indexed_contacts = [(c, idx) for c, idx in indexed_contacts if 
                           query_lower in c.get('call', '').lower() or
                           query_lower in c.get('country', '').lower() or
                           query_lower in c.get('state', '').lower() or
                           query_lower in c.get('gridsquare', '').lower()]
    
    if call_filter:
        call_filter_lower = call_filter.lower()
        indexed_contacts = [(c, idx) for c, idx in indexed_contacts if call_filter_lower in c.get('call', '').lower()]
    
    if grid_filter:
        grid_filter_lower = grid_filter.lower()
        indexed_contacts = [(c, idx) for c, idx in indexed_contacts if grid_filter_lower in c.get('gridsquare', '').lower()]
    
    if band_filter:
        indexed_contacts = [(c, idx) for c, idx in indexed_contacts if c.get('band', '').upper() == band_filter.upper()]
    
    if mode_filter:
        indexed_contacts = [(c, idx) for c, idx in indexed_contacts if c.get('mode', '').upper() == mode_filter.upper()]
    
    if date_from:
        indexed_contacts = [(c, idx) for c, idx in indexed_contacts if c.get('qso_date', '') >= date_from]
    
    if date_to:
        indexed_contacts = [(c, idx) for c, idx in indexed_contacts if c.get('qso_date', '') <= date_to]
    
    # Sort filtered contacts by date/time in descending order (newest first)
    indexed_contacts.sort(key=lambda x: (x[0].get('qso_date', ''), x[0].get('time_on', '')), reverse=True)
    
    # Pagination
    config = load_config()
    per_page = config.get('display', {}).get('contacts_per_page', 50)
    total_results = len(indexed_contacts)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    paginated_indexed_contacts = indexed_contacts[start_idx:end_idx]
    
    total_pages = (total_results + per_page - 1) // per_page
    has_prev = page > 1
    has_next = page < total_pages
    
    # Get unique bands and modes for dropdowns
    unique_bands = sorted(set(c.get('band', '').upper() for c in all_contacts if c.get('band')))
    unique_modes = sorted(set(c.get('mode', '').upper() for c in all_contacts if c.get('mode')))
    
    return render_template('search.html',
                         contacts=paginated_indexed_contacts,
                         query=query,
                         call_filter=call_filter,
                         grid_filter=grid_filter,
                         band_filter=band_filter,
                         mode_filter=mode_filter,
                         date_from=date_from,
                         date_to=date_to,
                         unique_bands=unique_bands,
                         unique_modes=unique_modes,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         total_results=total_results)

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            flash('Successfully logged in!', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('admin_login.html')

@app.route('/admin_logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    flash('Successfully logged out!', 'success')
    return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin_panel():
    """Admin panel"""
    station_log = load_station_log()
    stats = {
        'total_contacts': len(station_log['contacts']),
        'last_updated': station_log['header'].get('last_updated', 'Never')
    }
    return render_template('admin_panel.html', stats=stats)

@app.route('/upload', methods=['POST'])
@admin_required
def upload_file():
    """Upload and process ADIF file"""
    if 'file' not in request.files:
        flash('No file selected!', 'error')
        return redirect(url_for('admin_panel'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected!', 'error')
        return redirect(url_for('admin_panel'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Parse ADIF file
            parsed_data = parse_adif_file(filepath)
            
            # Load existing station log
            station_log = load_station_log()
            
            # Merge contacts (avoid duplicates, merge additional fields)
            new_contacts, updated_contacts = merge_contacts(station_log['contacts'], parsed_data['contacts'])
            
            # Update station log
            station_log['contacts'] = new_contacts
            station_log['header']['last_updated'] = datetime.datetime.now().isoformat()
            station_log['header']['total_contacts'] = len(new_contacts)
            
            # Merge header information
            for key, value in parsed_data['header'].items():
                if key not in ['created_timestamp', 'last_updated', 'total_contacts']:
                    station_log['header'][key] = value
            
            # Save updated log
            save_station_log(station_log)
            
            flash(f'Successfully processed ADIF file! Added {len(parsed_data["contacts"]) - updated_contacts} new contacts, updated {updated_contacts} existing contacts.', 'success')
            
            # Clean up uploaded file
            os.remove(filepath)
            
        except Exception as e:
            flash(f'Error processing ADIF file: {str(e)}', 'error')
            logging.error(f"ADIF processing error: {str(e)}")
            if os.path.exists(filepath):
                os.remove(filepath)
    else:
        flash('Invalid file type! Please upload .adi, .adif, or .txt files.', 'error')
    
    return redirect(url_for('admin_panel'))

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'adi', 'adif', 'txt'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/export/json')
@admin_required
def export_json():
    """Export station log as JSON"""
    station_log = load_station_log()
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"station_log_{timestamp}.json"
    
    # Create temporary file
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(temp_path, 'w') as f:
        json.dump(station_log, f, indent=2)
    
    return send_file(temp_path, as_attachment=True, download_name=filename)

@app.route('/export/adif')
@admin_required
def export_adif():
    """Export station log as ADIF"""
    from adif_parser import contacts_to_adif
    
    station_log = load_station_log()
    adif_content = contacts_to_adif(station_log['contacts'], station_log['header'])
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"station_log_{timestamp}.adi"
    
    # Create temporary file
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    with open(temp_path, 'w') as f:
        f.write(adif_content)
    
    return send_file(temp_path, as_attachment=True, download_name=filename)

@app.route('/qsl/<int:contact_index>')
def generate_qsl(contact_index):
    """Generate QSL card for contact"""
    station_log = load_station_log()
    
    if contact_index < 0 or contact_index >= len(station_log['contacts']):
        abort(404)
    
    contact = station_log['contacts'][contact_index]
    
    try:
        qsl_path = generate_qsl_card(contact, station_log['header'])
        return send_file(qsl_path, as_attachment=True)
    except Exception as e:
        flash(f'Error generating QSL card: {str(e)}', 'error')
        logging.error(f"QSL generation error: {str(e)}")
        return redirect(url_for('contact_details', contact_index=contact_index))

@app.route('/blog_management')
@admin_required
def blog_management():
    """Blog management page"""
    blog_posts = load_blog_posts()
    posts = blog_posts['posts'][::-1]  # Show newest first
    return render_template('blog_management.html', posts=posts)

@app.route('/blog_new', methods=['GET', 'POST'])
@admin_required
def blog_new():
    """Create new blog post"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        excerpt = request.form.get('excerpt', '').strip()
        
        if not title or not content:
            flash('Title and content are required!', 'error')
            return render_template('blog_edit.html', post=None, mode='new')
        
        blog_posts = load_blog_posts()
        
        new_post = {
            'id': blog_posts['next_id'],
            'title': title,
            'content': content,
            'excerpt': excerpt,
            'date': datetime.datetime.now().strftime('%Y-%m-%d')
        }
        
        blog_posts['posts'].append(new_post)
        blog_posts['next_id'] += 1
        
        save_blog_posts(blog_posts)
        flash('Blog post created successfully!', 'success')
        return redirect(url_for('blog_management'))
    
    return render_template('blog_edit.html', post=None, mode='new')

@app.route('/blog_edit/<int:post_id>', methods=['GET', 'POST'])
@admin_required
def blog_edit(post_id):
    """Edit existing blog post"""
    blog_posts = load_blog_posts()
    post = next((p for p in blog_posts['posts'] if p['id'] == post_id), None)
    
    if not post:
        abort(404)
    
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        excerpt = request.form.get('excerpt', '').strip()
        
        if not title or not content:
            flash('Title and content are required!', 'error')
            return render_template('blog_edit.html', post=post, mode='edit')
        
        post['title'] = title
        post['content'] = content
        post['excerpt'] = excerpt
        
        save_blog_posts(blog_posts)
        flash('Blog post updated successfully!', 'success')
        return redirect(url_for('blog_management'))
    
    return render_template('blog_edit.html', post=post, mode='edit')

@app.route('/blog_delete/<int:post_id>', methods=['POST'])
@admin_required
def blog_delete(post_id):
    """Delete blog post"""
    blog_posts = load_blog_posts()
    blog_posts['posts'] = [p for p in blog_posts['posts'] if p['id'] != post_id]
    
    save_blog_posts(blog_posts)
    flash('Blog post deleted successfully!', 'success')
    return redirect(url_for('blog_management'))

@app.route('/config_management')
@admin_required
def config_management():
    """Configuration management page"""
    config = load_config()
    return render_template('config_management.html', config=config)

@app.route('/config_update', methods=['POST'])
@admin_required
def config_update():
    """Update configuration settings"""
    config = load_config()
    
    # Station settings
    config['station']['call_sign'] = request.form.get('call_sign', '').strip().upper()
    config['station']['operator_name'] = request.form.get('operator_name', '').strip()
    config['station']['qth'] = request.form.get('qth', '').strip()
    config['station']['grid_square'] = request.form.get('grid_square', '').strip().upper()
    config['station']['email'] = request.form.get('email', '').strip()
    
    # Site settings
    config['site']['title'] = request.form.get('site_title', '').strip()
    config['site']['subtitle'] = request.form.get('site_subtitle', '').strip()
    config['site']['description'] = request.form.get('site_description', '').strip()
    config['site']['admin_password'] = request.form.get('admin_password', '').strip()
    
    # QSL settings
    config['qsl']['default_message'] = request.form.get('qsl_message', '').strip()
    config['qsl']['equipment'] = request.form.get('equipment', '').strip()
    config['qsl']['antenna'] = request.form.get('antenna', '').strip()
    config['qsl']['power'] = request.form.get('power', '').strip()
    
    # Display settings
    config['display']['contacts_per_page'] = int(request.form.get('contacts_per_page', 50))
    config['display']['recent_contacts_limit'] = int(request.form.get('recent_contacts_limit', 10))
    
    if save_config(config):
        flash('Configuration updated successfully! Changes will take effect after restart.', 'success')
    else:
        flash('Error saving configuration!', 'error')
    
    return redirect(url_for('config_management'))
